"""Find Me — search every camera for a vehicle or a person by photo.
Mounted at /api/search. Officer PIN required — this is a search over
everyone the cameras have ever seen, and Part 6 (audit trail) exists
because that carries a responsibility.
SQL narrows, numpy ranks — the same pattern as incident matching, just
without an incident: the query photo itself is the origin.
"""
import logging
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.core.security import require_pin
from app.db.queries import sightings as sightings_q
from app.db.session import get_connection
from app.services import matching as matching_service
from app.services.pipeline_client import process_frame

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/search", tags=["search"], dependencies=[Depends(require_pin)])

MAX_QUERY_BYTES = 8 * 1024 * 1024


def _crop_url(crop_path: Optional[str]) -> Optional[str]:
    return f"/evidence/{crop_path}" if crop_path else None


def _parse_ts(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Bad timestamp: {raw!r}")
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


@router.post("")
async def search(
    image: Annotated[UploadFile, File(description="Photo of the vehicle or person to find")],
    mode: Annotated[str, Form()] = "vehicle",
    from_ts: Annotated[Optional[str], Form()] = None,
    to_ts: Annotated[Optional[str], Form()] = None,
    camera_ids: Annotated[Optional[list[str]], Form()] = None,
    vehicle_type: Annotated[Optional[str], Form()] = None,
    select_index: Annotated[int, Form()] = 0,
    limit: Annotated[int, Form()] = 20,
) -> dict:
    """
    mode: "vehicle" (ranks on veh_emb) or "person" (ranks on rider_emb).
    If the uploaded photo has more than one vehicle, the first call returns
    all detections (status 300-style payload) and the officer re-calls with
    select_index set to the one they mean.
    """
    if mode not in ("vehicle", "person"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "mode must be 'vehicle' or 'person'")

    if image.size is not None and image.size > MAX_QUERY_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Image too large")
    payload = await image.read()
    if not payload:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty image")

    # Run the query photo through the same process_frame every camera frame
    # goes through. No fallback to embedding the whole photo — a picture of
    # a street is not a query (FIND_ME_PLAN.md Phase 1).
    detections = process_frame(payload, "find-me-query", datetime.now(timezone.utc).isoformat())

    if not detections:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "No vehicle found in that photo. Crop it closer to the bike.",
        )

    if len(detections) > 1 and select_index == 0:
        # More than one vehicle and the officer hasn't told us which yet —
        # hand back the list rather than guessing (FIND_ME_PLAN.md rule).
        return {
            "detail": "multiple_detections",
            "detections": [
                {
                    "index": i,
                    "vehicle_type": d.get("vehicle_type"),
                    "bbox": d.get("bbox"),
                }
                for i, d in enumerate(detections)
            ],
        }

    if select_index < 0 or select_index >= len(detections):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "select_index out of range")

    chosen = detections[select_index]
    embedding_field = "veh_emb" if mode == "vehicle" else "rider_emb"
    query_embedding = chosen.get(embedding_field)

    if query_embedding is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"No {'rider' if mode == 'person' else 'vehicle'} embedding in that photo.",
        )

    parsed_from = _parse_ts(from_ts)
    parsed_to = _parse_ts(to_ts)
    parsed_cameras = [c for c in (camera_ids or []) if c]

    with get_connection() as conn:
        candidates = sightings_q.search_sightings(
            conn,
            from_ts=parsed_from,
            to_ts=parsed_to,
            camera_ids=parsed_cameras or None,
            vehicle_type=vehicle_type,
            limit=2000,
        )

    ranked = matching_service.rank_by_cosine(
        query_embedding, candidates, top_k=limit, embedding_field=embedding_field
    )

    logger.info(
        "search: mode=%s query_detections=%d candidates=%d results=%d",
        mode, len(detections), len(candidates), len(ranked),
    )

    return {
        "query_detections": len(detections),
        "selected_index": select_index,
        "results": [
            {
                "sighting_id": c["id"],
                "score": round(score, 4),
                "ts": c["ts"],
                "vehicle_type": c["vehicle_type"],
                "crop_url": _crop_url(c.get("crop_path")),
                "camera": {"id": c["camera_id"], "name": c["camera_name"]},
            }
            for c, score in ranked
        ],
    }
