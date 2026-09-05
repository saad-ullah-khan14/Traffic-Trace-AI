r"""Populate candidate matches for existing incidents, for UI testing.

Phase 11 does this properly: triggered on incident creation, and fused through
pipeline.score_candidates. This script exists only so the review screen has
something to show before that lands — it uses the same find_candidates path,
with the raw visual similarity as the score.

    .\.venv\Scripts\python.exe -m scripts.seed_matches
"""

import sys

from app.db.queries import cameras as cameras_q
from app.db.queries import incidents as incidents_q
from app.db.queries import matches as matches_q
from app.db.queries import sightings as sightings_q
from app.db.session import get_connection
from app.services.matching import find_candidates


def main() -> int:
    with get_connection() as conn:
        cameras = cameras_q.list_cameras(conn)
        open_incidents = incidents_q.list_incidents(conn, limit=200)
        if not open_incidents:
            print("no incidents — post a frame with a violation first")
            return 1

        total = 0
        for incident in open_incidents:
            origin = sightings_q.get_sighting(conn, incident["sighting_id"])
            if origin is None:
                continue

            ranked = find_candidates(conn, origin, cameras)
            if not ranked:
                continue

            matches_q.save_matches(
                conn,
                incident_id=incident["id"],
                scored=[
                    (
                        candidate["id"],
                        float(score),
                        # Only the visual signal exists until score_candidates
                        # lands; showing one bar is honest, inventing four is not.
                        {"vehicle": round(float(score), 4)},
                    )
                    for candidate, score in ranked
                ],
            )
            total += len(ranked)
            print(f"  incident {str(incident['id'])[:8]} -> {len(ranked)} candidates")

    print(f"\n{total} matches written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
