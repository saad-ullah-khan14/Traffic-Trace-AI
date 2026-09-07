"""What an officer's decision means beyond storing it.

Kept out of the route so the route stays a thin adapter, and out of
services/matching.py so ranking has nothing to do with decisions.
"""

import logging
from typing import Any, Optional
from uuid import UUID

from app.db.queries import incidents as incidents_q

logger = logging.getLogger(__name__)


def absorb_duplicate_case(conn, incident_id: UUID, sighting_id: UUID) -> Optional[dict[str, Any]]:
    """A confirmed match means two cases are one offender. Fold them.

    Every violation opens a case, because at ingest time nothing can reliably
    say whether two helmetless riders are the same person. So one rider crossing
    three cameras leaves three cases, each holding the others as candidates —
    accurate, but three cards for one offence.

    Confirming a candidate is the officer stating they are the same vehicle. If
    that sighting had opened a case of its own, this is the moment it stops being
    separate: it is folded into this one and leaves the feed. Its evidence is not
    deleted and the row remains, so the merge is a presentation decision made on
    a human's judgement, not a guess we can get wrong.

    Grouping automatically on a similarity score was tried first and abandoned.
    Measured on real footage:

        the SAME rider across two cameras   0.52 - 0.55
        six DIFFERENT riders                0.69 - 0.75

    The same vehicle scores LOWER than different ones. The overlap is not a
    tuning problem, it is the wrong way round, and no threshold fixes it. The
    officer is the only signal that actually knows.

    Returns None when there was nothing to fold — the common case.
    """
    duplicate = incidents_q.get_incident_for_sighting(conn, sighting_id)
    if duplicate is None or duplicate["id"] == incident_id:
        return None

    merged = incidents_q.merge_into(conn, duplicate["id"], into=incident_id)
    if merged is None:
        return None

    logger.info(
        "case %s folded into %s - the officer confirmed they are one vehicle",
        duplicate["id"],
        incident_id,
    )
    return {"merged_id": str(duplicate["id"]), "into_id": str(incident_id)}


def get_confirmed_sighting_ids(conn) -> set[str]:
    """
    Every sighting_id that has already been confirmed as the same vehicle
    for SOME incident. Used to keep a confirmed sighting from being
    re-offered as a candidate on an unrelated incident.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT sighting_id FROM matches WHERE decision = 'confirm'"
        )
        return {str(row["sighting_id"]) for row in cur.fetchall()}