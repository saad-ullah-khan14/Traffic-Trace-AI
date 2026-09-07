"""
Standalone test: does filtering candidates by attrs.color BEFORE ranking
(rather than blending it as a score) put the correct match at rank-1 more
often than raw CLIP cosine alone?

This does NOT touch production code. It reads real sightings from the
database, picks each incident's origin sighting as a "query", and compares
two strategies:
  A) raw cosine only (what search.py does today)
  B) color-filter first (only candidates with the SAME attrs.color), then
     cosine rank within that subset

Run from api/ with the venv active:
    python test_color_filter_idea.py
"""
import sys
sys.path.insert(0, ".")

import numpy as np
from app.db.session import get_connection


def cosine(a, b):
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(a @ b / denom) if denom else 0.0


def main():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT i.id AS incident_id, i.sighting_id AS origin_id
                FROM incidents i
                """
            )
            incidents = cur.fetchall()

        with conn.cursor(binary=True) as cur:
            cur.execute(
                "SELECT id, veh_emb, attrs, camera_id, ts FROM sightings WHERE veh_emb IS NOT NULL"
            )
            all_sightings = {str(r["id"]): dict(r) for r in cur.fetchall()}

    print(f"Testing {len(incidents)} incidents against {len(all_sightings)} total sightings\n")

    a_hits = b_hits = tested = 0

    for inc in incidents:
        origin_id = str(inc["origin_id"])
        origin = all_sightings.get(origin_id)
        if not origin:
            continue

        others = [(sid, s) for sid, s in all_sightings.items() if sid != origin_id]
        if len(others) < 2:
            continue  # need at least 2 candidates for ranking to mean anything

        tested += 1
        origin_color = (origin.get("attrs") or {}).get("color")

        # Strategy A: raw cosine over ALL others
        scored_a = sorted(
            others, key=lambda pair: cosine(origin["veh_emb"], pair[1]["veh_emb"]), reverse=True
        )
        rank1_a = scored_a[0][0]

        # Strategy B: filter to same color first (if any exist), then cosine
        same_color = [(sid, s) for sid, s in others if (s.get("attrs") or {}).get("color") == origin_color]
        pool_b = same_color if same_color else others
        scored_b = sorted(
            pool_b, key=lambda pair: cosine(origin["veh_emb"], pair[1]["veh_emb"]), reverse=True
        )
        rank1_b = scored_b[0][0]

        print(f"incident (origin colour={origin_color}):")
        print(f"  A (raw cosine)     rank-1 = {rank1_a[:8]}")
        print(f"  B (colour-filter)  rank-1 = {rank1_b[:8]}  (pool size {len(pool_b)} of {len(others)})")
        print()

    print(f"Tested {tested} incidents. Compare the rank-1 IDs above by eye against")
    print("what you know to be the correct match for each incident.")


if __name__ == "__main__":
    main()
