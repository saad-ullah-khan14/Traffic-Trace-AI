"""Find Me — search every camera for a vehicle or a person by photo.
Mounted at /api/search. Officer PIN required — this is a search over
everyone the cameras have ever seen, and Part 6 (audit trail) exists
because that carries a responsibility.
SQL narrows, numpy ranks — the same pattern as incident matching, just
without an incident: the query photo itself is the origin.

Layering rule (FIND_ME_PLAN.md Phase 1): the route contains no SQL — all
of it lives in db/queries/search_audit.py and db/queries/sightings.py.
"""
import hashlib
import logging
from datetime import datetime, timezone
from typing import Annotated, Optional
from uuid import UUID

import cv2
import numpy as np
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile, status

from app.core.security import require_pin
from app.db.queries import search_audit as search_audit_q
from app.db.queries import sightings as sightings_q
from app.db.session import get_connection
from app.services import matching as matching_service
from app.services.pipeline_client import fingerprint, process_frame, score_candidates

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/search", tags=["search"], dependencies=[Depends(require_pin)])

MAX_QUERY_BYTES = 8 * 1024 * 1024


def _crop_url(crop_path: Optional[str]) -> Optional[str]:
    return f"/evidence/{crop_path}" if crop_path else None


def _frame_url(frame_path: Optional[str]) -> Optional[str]:
    return f"/{frame_path}" if frame_path else None


def _decode_image(payload: bytes):
    arr = np.frombuffer(payload, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


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

    detections = process_frame(payload, "find-me-query", datetime.now(timezone.utc).isoformat())

    if not detections:
        # Fallback for a query photo that is ALREADY a tight crop (e.g. an
        # evidence/ file re-uploaded) — the detector expects a full street
        # scene and often finds nothing on a pre-cropped, zoomed-in image.
        # Since there's nothing else in the frame to detect, embed the whole
        # image directly as the vehicle.
        image_array = _decode_image(payload)
        if image_array is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "No vehicle found in that photo. Crop it closer to the bike.",
            )
        fp = fingerprint(image_array)
        detections = [
            {
                "vehicle_type": "unknown",
                "bbox": [0, 0, image_array.shape[1], image_array.shape[0]],
                "veh_emb": fp["veh_emb"],
                "rider_emb": fp["rider_emb"],
                "attrs": fp["attrs"],
                "violations": [],
                "confidence": None,
            }
        ]

    if len(detections) > 1 and select_index == 0:
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

                # Re-rank purely on visual embedding first (rank_by_cosine's own
        # top_k*2 buffer, so the color-blend below has enough candidates
        # to actually re-order, not just re-sort the same top 20).
                # First narrow with raw cosine (cheap, over ALL candidates), THEN
        # re-score the top slice with the same fused scorer incident-matching
        # uses (vehicle + rider + colour) — this is the scorer actually
        # measured accurate (margin +0.027, rank-1 3/3), unlike raw CLIP
        # alone which was only ever a fallback.
        pre_ranked = matching_service.rank_by_cosine(
            query_embedding, candidates, top_k=limit * 3, embedding_field=embedding_field
        )

        synthetic_origin = {
            "id": "query",
            "camera_id": "query",
            "ts": datetime.now(timezone.utc),
            "vehicle_type": chosen.get("vehicle_type"),
            "veh_emb": chosen.get("veh_emb"),
            "rider_emb": chosen.get("rider_emb"),
            "attrs": chosen.get("attrs") or {},
        }
        incident_payload, candidate_payloads = matching_service.build_scoring_payload(
            synthetic_origin, pre_ranked
        )
        scored = score_candidates(incident_payload, candidate_payloads)
        scored.sort(key=lambda r: r["score"], reverse=True)

        by_id = {str(c["id"]): c for c, _ in pre_ranked}
        ranked = [
            (by_id[row["sighting_id"]], row["score"])
            for row in scored[:limit]
            if row["sighting_id"] in by_id
        ]
        logger.info(
            "search: mode=%s query_detections=%d candidates=%d results=%d",
            mode, len(detections), len(candidates), len(ranked),
        )

        # Phase 6 of FIND_ME_PLAN.md: one audit row per search, whether it
        # found anything or not.
        search_id = search_audit_q.insert_search_audit(
            conn,
            mode=mode,
            query_image_hash=hashlib.sha256(payload).hexdigest(),
            from_ts=parsed_from,
            to_ts=parsed_to,
            camera_ids=parsed_cameras or None,
            vehicle_type=vehicle_type,
            result_count=len(ranked),
        )

    return {
        "search_id": search_id,
        "query_detections": len(detections),
        "selected_index": select_index,
        "results": [
            {
                "sighting_id": c["id"],
                "score": round(score, 4),
                "ts": c["ts"],
                "vehicle_type": c["vehicle_type"],
                "crop_url": _crop_url(c.get("crop_path")),
                "frame_url": _frame_url(c.get("frame_path")),
                "camera": {
                    "id": c["camera_id"],
                    "name": c["camera_name"],
                    "lat": c.get("lat"),
                    "lng": c.get("lng"),
                },
            }
            for c, score in ranked
        ],
    }


@router.post("/{search_id}/decision")
def decide_result(
    search_id: UUID,
    sighting_id: Annotated[UUID, Body()],
    decision: Annotated[str, Body()],
) -> dict:
    """
    Persist an officer's confirm/reject on one Find Me result.

    Without this, a decision only ever existed in the browser's React
    state — a page refresh lost it, search_audit.confirmed_count never
    moved, and Phase 5's benchmark had no officer-labelled ground truth
    to measure against (FIND_ME_PLAN.md rule 1: never measure on
    synthetic input).
    """
    if decision not in ("confirm", "reject"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "decision must be 'confirm' or 'reject'")

    with get_connection() as conn:
        if search_audit_q.get_search_audit(conn, search_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "search_id not found")

        row = search_audit_q.insert_search_confirmation(conn, search_id, sighting_id, decision)

    return {"id": row["id"], "decision": decision, "decided_at": row["decided_at"]}