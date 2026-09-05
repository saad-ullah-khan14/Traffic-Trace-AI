"""Delete sightings nobody is using, after 48 hours.

This is the privacy claim in the pitch, so it has to actually run. A sighting is
kept only while it is evidence: linked to an incident, or proposed as a match.
Everything else — the overwhelming majority, since every passing vehicle is
recorded — expires.

A periodic task rather than a database trigger, so it can be paused during a
demo without touching the schema.
"""

import asyncio
import logging
from pathlib import Path

from app.core.config import settings
from app.db.session import get_connection

logger = logging.getLogger(__name__)

RETENTION_HOURS = 48
SWEEP_INTERVAL_SECONDS = 60 * 60


def sweep_once() -> dict[str, int]:
    """Delete expired unlinked sightings and their crop files."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM sightings s
                WHERE s.ts < now() - make_interval(hours => %s)
                  AND NOT EXISTS (SELECT 1 FROM incidents i WHERE i.sighting_id = s.id)
                  AND NOT EXISTS (SELECT 1 FROM matches   m WHERE m.sighting_id = s.id)
                RETURNING s.crop_path
                """,
                (RETENTION_HOURS,),
            )
            paths = [row["crop_path"] for row in cur.fetchall() if row["crop_path"]]

    # Only delete a file once no surviving row references it — crops are
    # content-addressed, so two sightings can legitimately share one.
    removed = 0
    if paths:
        evidence_dir = Path(settings.EVIDENCE_DIR).resolve()
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT crop_path FROM sightings WHERE crop_path = ANY(%s)",
                (paths,),
            )
            still_used = {row["crop_path"] for row in cur.fetchall()}

        for name in set(paths) - still_used:
            try:
                (evidence_dir / name).unlink(missing_ok=True)
                removed += 1
            except OSError:
                pass

    if paths or removed:
        logger.info("retention sweep: %d sightings, %d crops removed", len(paths), removed)
    return {"sightings": len(paths), "crops": removed}


async def run_forever() -> None:
    while True:
        try:
            await asyncio.to_thread(sweep_once)
        except asyncio.CancelledError:
            raise
        except Exception:
            # A failed sweep must never take the API down with it.
            logger.exception("retention sweep failed")
        await asyncio.sleep(SWEEP_INTERVAL_SECONDS)
