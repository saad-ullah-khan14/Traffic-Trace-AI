"""The officer's decision. Mounted at /api/matches.

Human-in-the-loop by design: the system proposes, a person decides. Nothing is
ever auto-confirmed, and that is a claim the pitch makes explicitly.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.events import publish
from app.core.security import require_pin
from app.db.queries import incidents as incidents_q
from app.db.queries import matches as matches_q
from app.db.session import get_connection
from app.services import journeys as journeys_service
from app.services import matches as matches_service
from app.schemas.incidents import DecisionIn, DecisionOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/matches", tags=["matches"])

VALID_DECISIONS = {"confirm", "reject"}


@router.post(
    "/{match_id}/decision",
    response_model=DecisionOut,
    dependencies=[Depends(require_pin)],
)
async def decide(match_id: UUID, payload: DecisionIn) -> dict:
    if payload.decision not in VALID_DECISIONS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"decision must be one of {sorted(VALID_DECISIONS)}",
        )

    with get_connection() as conn:
        decided = matches_q.decide_match(conn, match_id, payload.decision)
        if decided is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Match not found")

        # A confirmed match means the officer has identified the vehicle, so the
        # incident is no longer just "open". Phase 13 hangs journey building off
        # this same moment.
        journey = None
        merged = None
        if payload.decision == "confirm":
            incidents_q.set_incident_status(conn, decided["incident_id"], "confirmed")

            # Two cases, one offender. The officer has just said so, which is the
            # only thing that reliably knows — see absorb_duplicate_case.
            merged = matches_service.absorb_duplicate_case(
                conn, decided["incident_id"], decided["sighting_id"]
            )

            # Rebuild rather than append: the route is derived from whatever is
            # confirmed right now, so there is no stale copy to keep in step.
            journey = journeys_service.rebuild_journey(conn, decided["incident_id"])

    logger.info("match %s %sed", match_id, payload.decision)

    await publish(
        "match_decision",
        {
            "match_id": str(decided["id"]),
            "incident_id": str(decided["incident_id"]),
            "sighting_id": str(decided["sighting_id"]),
            "decision": decided["decision"],
        },
    )
    if journey:
        await publish("journey_update", journey)

    if merged is not None:
        await publish("incident_merged", merged)

    return decided
