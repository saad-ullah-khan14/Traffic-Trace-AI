r"""Phase 3 acceptance test: gated SQL query + numpy top-5 in under 50 ms.

Fills the database with synthetic sightings, then times the real matching path
end to end. Cleans up after itself unless --keep is passed.

    cd api
    .\.venv\Scripts\python.exe -m scripts.bench_matching
    .\.venv\Scripts\python.exe -m scripts.bench_matching --rows 20000
"""

import argparse
import random
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone

import numpy as np

from app.core.constants import EMBEDDING_DIM, MATCH_WINDOW_SECONDS
from app.db.queries import cameras as cameras_q
from app.db.queries import sightings as sightings_q
from app.db.session import get_connection
from app.services.geo import build_gate
from app.services.matching import find_candidates, rank_by_cosine

BENCH_TAG = "__bench__"
VEHICLE_TYPES = ["motorcycle", "car", "rickshaw", "truck"]


def random_unit_vector(rng: np.random.Generator) -> list[float]:
    """A normalized embedding, mimicking what process_frame will produce."""
    vec = rng.standard_normal(EMBEDDING_DIM).astype(np.float32)
    return (vec / np.linalg.norm(vec)).tolist()


def seed_sightings(conn, cameras, rows: int, rng: np.random.Generator) -> None:
    now = datetime.now(timezone.utc)
    print(f"inserting {rows} synthetic sightings across {len(cameras)} cameras ...")

    payload = []
    for _ in range(rows):
        camera = random.choice(cameras)
        payload.append(
            (
                camera["id"],
                now - timedelta(seconds=random.uniform(0, MATCH_WINDOW_SECONDS)),
                random.choice(VEHICLE_TYPES),
                '[0,0,100,200]',
                random_unit_vector(rng),
                None,
                '{"bench": true}',
                round(random.uniform(0.5, 1.0), 3),
                BENCH_TAG,
            )
        )

    started = time.perf_counter()
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO sightings (
                camera_id, ts, vehicle_type, bbox, veh_emb, rider_emb,
                attrs, confidence, crop_path
            )
            VALUES (%s, %s, %s, %s::jsonb, %s::real[], %s::real[], %s::jsonb, %s, %s)
            """,
            payload,
        )
    conn.commit()
    print(f"  inserted in {time.perf_counter() - started:.1f}s")


def cleanup(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM sightings WHERE crop_path = %s", (BENCH_TAG,))
        removed = cur.rowcount
    conn.commit()
    print(f"cleaned up {removed} benchmark rows")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=5000, help="synthetic sightings to insert")
    parser.add_argument("--runs", type=int, default=20, help="timed iterations")
    parser.add_argument("--keep", action="store_true", help="leave benchmark rows in the database")
    args = parser.parse_args()

    rng = np.random.default_rng(42)

    with get_connection() as conn:
        cameras = cameras_q.list_cameras(conn)
        if len(cameras) < 2:
            print("ERROR: seed cameras first -> python -m scripts.seed_cameras")
            return 1

        seed_sightings(conn, cameras, args.rows, rng)

        origin_camera = cameras[0]
        query_embedding = random_unit_vector(rng)
        # Mid-window, so candidates exist both before and after the incident.
        # Anchoring at "now" would leave the forward scan empty and understate
        # how much work the gate really does.
        origin_ts = datetime.now(timezone.utc) - timedelta(seconds=MATCH_WINDOW_SECONDS / 2)
        camera_ids, min_gaps = build_gate(
            origin_camera["lat"], origin_camera["lng"], cameras, origin_camera["id"]
        )

        print(f"\ntiming {args.runs} runs of: space-time gate + numpy top-5\n")

        gate_ms, rank_ms, total_ms, gated_counts = [], [], [], []

        for _ in range(args.runs):
            t0 = time.perf_counter()
            gated = sightings_q.get_gated_candidates(
                conn,
                origin_ts=origin_ts,
                exclude_sighting_id=origin_camera["id"],  # any uuid not in the set
                camera_ids=camera_ids,
                min_gap_seconds=min_gaps,
                window_seconds=MATCH_WINDOW_SECONDS,
            )
            t1 = time.perf_counter()
            ranked = rank_by_cosine(query_embedding, gated, top_k=5)
            t2 = time.perf_counter()

            gate_ms.append((t1 - t0) * 1000)
            rank_ms.append((t2 - t1) * 1000)
            total_ms.append((t2 - t0) * 1000)
            gated_counts.append(len(gated))

        # End-to-end through the real service entry point, which also hydrates
        # the surviving candidates with their crops, attrs and camera details.
        with conn.cursor(binary=True) as cur:
            cur.execute(
                "SELECT id, camera_id, ts, veh_emb FROM sightings WHERE crop_path = %s LIMIT 1",
                (BENCH_TAG,),
            )
            origin = cur.fetchone()

        e2e_ms = []
        for _ in range(args.runs):
            t0 = time.perf_counter()
            e2e = find_candidates(conn, origin, cameras, top_k=5)
            e2e_ms.append((time.perf_counter() - t0) * 1000)

        total_rows = sightings_q.count_sightings(conn)

        def report(label: str, values: list[float]) -> None:
            print(
                f"  {label:<22} median {statistics.median(values):6.2f} ms   "
                f"min {min(values):6.2f}   max {max(values):6.2f}"
            )

        print(f"  sightings in table:    {total_rows}")
        print(f"  candidates per gate:   {gated_counts[0]}")
        print(f"  top-5 returned:        {len(ranked)}")
        print()
        report("SQL space-time gate", gate_ms)
        report("numpy cosine top-5", rank_ms)
        report("TOTAL", total_ms)
        print()
        report("find_candidates (e2e)", e2e_ms)
        print(f"  {'':<22} ^ gate + rank + hydrate {len(e2e)} survivors")

        median_total = statistics.median(e2e_ms)
        budget_ok = median_total < 50.0
        print()
        print(
            f"  {'PASS' if budget_ok else 'FAIL'}: median {median_total:.2f} ms "
            f"{'<' if budget_ok else '>='} 50 ms budget"
        )

        if ranked:
            print(f"\n  best similarity: {ranked[0][1]:.4f}   worst of top-5: {ranked[-1][1]:.4f}")
            print("  (random vectors, so ~0.0 is expected — real embeddings cluster much higher)")

        if not args.keep:
            print()
            cleanup(conn)

    return 0 if budget_ok else 1


if __name__ == "__main__":
    sys.exit(main())
