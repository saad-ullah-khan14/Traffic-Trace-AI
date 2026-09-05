"""Journey for one incident. Mounted at /api/journeys."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.db.session import get_connection
from app.services import journeys as journeys_service

router = APIRouter(prefix="/journeys", tags=["journeys"])


@router.get("/{incident_id}")
def get_journey(incident_id: UUID) -> dict:
    """The confirmed route, oldest stop first.

    404 until at least one match is confirmed — a single stop is a violation,
    not a journey.
    """
    with get_connection() as conn:
        journey = journeys_service.get_journey(conn, incident_id)

    if journey is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No confirmed journey yet")
    return journey
