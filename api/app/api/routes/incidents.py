"""Incident feed and review screen. Mounted at /api/incidents."""

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.db.queries import incidents as incidents_q
from app.db.queries import matches as matches_q
from app.db.session import get_connection
from app.services import matching as matching_service
from app.schemas.incidents import IncidentDetail, IncidentListItem

router = APIRouter(prefix="/incidents", tags=["incidents"])


def _crop_url(crop_path: Optional[str]) -> Optional[str]:
    return f"/evidence/{crop_path}" if crop_path else None


def _sighting(row: dict[str, Any]) -> dict[str, Any]:
    """Flat DB row -> the nested shape the dashboard expects."""
    return {
        "id": row["sighting_id"],
        "ts": row["ts"],
        "vehicle_type": row["vehicle_type"],
        "attrs": row.get("attrs") or {},
        "confidence": row.get("confidence"),
        "crop_url": _crop_url(row.get("crop_path")),
        "crop_hash": row.get("crop_hash"),
        "camera": {
            "id": row["camera_id"],
            "name": row["camera_name"],
            "lat": row.get("lat"),
            "lng": row.get("lng"),
        },
    }


@router.get("", response_model=list[IncidentListItem])
def list_incidents(
    incident_status: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=50, le=200),
) -> list[dict]:
    """Newest first, for the feed."""
    with get_connection() as conn:
        rows = incidents_q.list_incidents(conn, status=incident_status, limit=limit)

    return [
        {
            "id": r["id"],
            "violation": r["violation"],
            "plate_text": r["plate_text"],
            "status": r["status"],
            "created_at": r["created_at"],
            "vehicle_type": r["vehicle_type"],
            "crop_url": _crop_url(r.get("crop_path")),
            "camera": {"id": r["camera_id"], "name": r["camera_name"]},
            "match_count": r["match_count"],
        }
        for r in rows
    ]


@router.get("/{incident_id}", response_model=IncidentDetail)
def get_incident(incident_id: UUID) -> dict:
    """Everything the review screen needs in one call.

    One request rather than three: the officer opens this while standing over a
    decision, and three round-trips on a hotspot is a visible stutter.
    """
    with get_connection() as conn:
        incident = incidents_q.get_incident(conn, incident_id)
        if incident is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found")

        # Re-rank first: sightings recorded since this incident opened are
        # exactly the ones an officer is here to look for. Costs ~40 ms and
        # never disturbs a decision already made.
        matching_service.refresh_candidates(conn, incident)

        matches = matches_q.get_matches_for_incident(conn, incident_id)

    return {
        "id": incident["id"],
        "violation": incident["violation"],
        "plate_text": incident["plate_text"],
        "status": incident["status"],
        "created_at": incident["created_at"],
        "sighting": _sighting(incident),
        "matches": [
            {
                "id": m["id"],
                "score": m["score"],
                "breakdown": m.get("breakdown") or {},
                "decision": m["decision"],
                "decided_at": m["decided_at"],
                "sighting": _sighting(m),
            }
            for m in matches
        ],
    }
