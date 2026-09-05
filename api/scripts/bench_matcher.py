r"""Does the FUSED score separate a true match from a false one? Measure the
real production path, not a stand-in.

    cd api
    .\.venv\Scripts\python.exe -m scripts.bench_matcher

`labelset/benchmark.py` scores a single embedding function, which is the right
tool for choosing an encoder — and the wrong one for everything else. It cannot
see a weight change, an attribute filter, or anything else inside
`pipeline.score_candidates`, because it never calls it. A change to `matcher.py`
that is validated only against that script is not validated at all.

This script closes that gap. It reads the officer's labels and the real stored
embeddings straight from the database, builds the payload with the very same
`build_scoring_payload` the API uses in production, and hands it to
`score_candidates`. Whatever `pipeline/` currently does is what gets measured.

Reports the same two numbers the labelset does, so they can be compared:

    margin   worst confirmed pair minus best rejected pair. Positive means one
             threshold separates them; negative means none can.
    rank-1   of the incidents with a confirmed match, how many rank it first.
             This is what the officer actually experiences.

Read-only. Safe to run during a demo.

One caveat that matters after any change to how crops are embedded: the vectors
in `sightings.veh_emb` were produced by whatever fingerprint was running when
they were ingested. If `fingerprint()` changes what it embeds — a different crop,
a different model — the stored vectors are from the OLD one, and this script
measures a mixture. Re-ingest, or reset and refilm, before trusting the number.
"""

import sys
from collections import defaultdict

import numpy as np

from app.core.constants import MIN_CANDIDATE_SCORE
from app.db.queries import sightings as sightings_q
from app.db.session import get_connection
from app.services.matching import build_scoring_payload
from app.services.pipeline_client import PIPELINE_AVAILABLE, PIPELINE_STATUS, score_candidates


def cosine(a, b):
    if a is None or b is None:
        return 0.0
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))


def main() -> int:
    if not PIPELINE_AVAILABLE:
        print(f"pipeline not available: {PIPELINE_STATUS}")
        return 1

    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT m.incident_id, m.sighting_id, m.decision,
                   i.sighting_id AS origin_id
            FROM matches m JOIN incidents i ON i.id = m.incident_id
            WHERE m.decision IS NOT NULL
            ORDER BY m.incident_id
            """
        )
        rows = cur.fetchall()

        if not rows:
            print("No labelled matches. Label the candidates on the review screen first.")
            return 1

        by_incident = defaultdict(list)
        origins = {}
        for row in rows:
            by_incident[row["incident_id"]].append(row)
            origins[row["incident_id"]] = row["origin_id"]

        wanted = set(origins.values()) | {r["sighting_id"] for r in rows}
        full = sightings_q.get_sightings_by_ids(conn, list(wanted))

    same_scores, diff_scores = [], []
    hits = total = 0

    print(f"\n  pipeline   {PIPELINE_STATUS}")
    print(f"  incidents  {len(by_incident)} with labelled candidates\n")

    for incident_id, labelled in by_incident.items():
        origin = full.get(origins[incident_id])
        if origin is None:
            continue

        candidates = [(full[r["sighting_id"]], r) for r in labelled
                      if r["sighting_id"] in full]
        if not candidates:
            continue

        ranked = [(cand, cosine(origin.get("veh_emb"), cand.get("veh_emb")))
                  for cand, _ in candidates]
        payload, candidate_payloads = build_scoring_payload(origin, ranked)
        scored = score_candidates(payload, candidate_payloads)

        truth = {str(r["sighting_id"]): r["decision"] == "confirm" for _, r in candidates}
        offered = {str(row["sighting_id"]): float(row["score"]) for row in scored}

        # A candidate the scorer dropped entirely is a rejection by the pipeline —
        # a hard attribute filter looks exactly like this, and it is invisible in
        # any benchmark that only scores pairs. Score it as 0.0 so a filtered-out
        # TRUE match shows up as the failure it is.
        print(f"  incident {str(incident_id)[:8]}")
        rows_out = []
        for sighting_id, is_same in truth.items():
            score = offered.get(sighting_id)
            dropped = score is None
            score = 0.0 if dropped else score
            rows_out.append((score, is_same, dropped))
            (same_scores if is_same else diff_scores).append(score)
            flag = "  <-- DROPPED by the scorer" if dropped else ""
            shown = "shown " if score >= MIN_CANDIDATE_SCORE else "hidden"
            print(f"    {'TRUE ' if is_same else 'false'} {score:.3f}  {shown}{flag}")

        if any(is_same for _, is_same, _ in rows_out):
            total += 1
            order = sorted(rows_out, key=lambda r: r[0], reverse=True)
            position = next(i for i, r in enumerate(order, 1) if r[1])
            hits += position == 1
            print(f"    true match at position {position} of {len(order)}"
                  f"  {'OK' if position == 1 else 'MISS'}")
        print()

    if not same_scores or not diff_scores:
        print("  Need at least one confirm AND one reject to compute a margin.")
        return 1

    margin = min(same_scores) - max(diff_scores)
    print("  FUSED SCORE  (pipeline.score_candidates, production path)")
    print(f"    confirmed   n={len(same_scores):<3} {min(same_scores):.3f} - {max(same_scores):.3f}")
    print(f"    rejected    n={len(diff_scores):<3} {min(diff_scores):.3f} - {max(diff_scores):.3f}")
    print(f"    margin      {margin:+.3f}   "
          f"{'SEPARATES' if margin > 0 else 'overlaps - no threshold works'}")
    print(f"    rank-1      {hits}/{total}")
    print(f"\n  Confirmed pairs: {len(same_scores)}. "
          f"{'Too few to conclude anything — collect more labels.' if len(same_scores) < 10 else ''}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
