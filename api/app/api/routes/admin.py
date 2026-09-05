"""Officer PIN check and the demo reset. Mounted at /api/admin."""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends

from app.core.config import settings
from app.core.security import require_pin
from app.db.session import get_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/verify-pin", dependencies=[Depends(require_pin)])
def verify_pin() -> dict:
    """Returns 200 if the PIN is right, 401 if not. The dashboard gate calls this."""
    return {"ok": True}


@router.post("/reset", dependencies=[Depends(require_pin)])
def reset_demo() -> dict:
    """Wipe sightings, incidents, matches and journeys. Keep the cameras.

    Cameras survive on purpose: their tokens are already typed into three
    phones, and re-registering mid-demo would cost minutes.

    One DELETE is enough — every other table cascades from sightings.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sightings")
            deleted = cur.rowcount

    removed = 0
    evidence_dir = Path(settings.EVIDENCE_DIR).resolve()
    for crop in evidence_dir.glob("*.jpg"):
        try:
            crop.unlink()
            removed += 1
        except OSError:
            pass

    logger.warning("DEMO RESET: %d sightings and %d crops deleted", deleted, removed)
    return {"sightings_deleted": deleted, "crops_deleted": removed}
