r"""Correctness test for the numpy float4[] loader.

A misparsed embedding would corrupt matching silently, which is far worse than
being slow — so this asserts exact round-trip equality before the speed-up is
trusted anywhere.

    cd api
    .\.venv\Scripts\python.exe -m scripts.test_numpy_loader
"""

import sys
from datetime import datetime, timezone

import numpy as np

from app.core.constants import EMBEDDING_DIM
from app.db.queries import cameras as cameras_q
from app.db.queries import sightings as sightings_q
from app.db.session import get_connection

TAG = "__loadertest__"


def main() -> int:
    rng = np.random.default_rng(1234)
    failures = []

    with get_connection() as conn:
        cameras = cameras_q.list_cameras(conn)
        if not cameras:
            print("ERROR: run scripts.seed_cameras first")
            return 1
        camera = cameras[0]

        with conn.cursor() as cur:
            cur.execute("DELETE FROM sightings WHERE crop_path = %s", (TAG,))

        # Values chosen to catch sign, exponent and precision errors, plus two
        # random vectors. float32 round-trip must be exact, not approximate.
        vectors = [
            np.linspace(-1.0, 1.0, EMBEDDING_DIM, dtype=np.float32),
            np.full(EMBEDDING_DIM, -0.5, dtype=np.float32),
            rng.standard_normal(EMBEDDING_DIM).astype(np.float32),
            rng.standard_normal(EMBEDDING_DIM).astype(np.float32),
        ]
        vectors[0][0] = np.float32(-123.456)
        vectors[0][-1] = np.float32(0.0)

        inserted = []
        for i, vec in enumerate(vectors):
            row = sightings_q.insert_sighting(
                conn,
                camera_id=camera["id"],
                ts=datetime.now(timezone.utc),
                vehicle_type="motorcycle",
                bbox=[0, 0, 10, 10],
                veh_emb=vec.tolist(),
                attrs={"i": i},
                crop_path=TAG,
            )
            inserted.append((row["id"], vec))
        conn.commit()

        print("checking binary (numpy) path against text (psycopg default) path\n")

        for sighting_id, original in inserted:
            with conn.cursor(binary=True) as cur:
                cur.execute("SELECT veh_emb FROM sightings WHERE id = %s", (sighting_id,))
                binary_value = cur.fetchone()["veh_emb"]

            with conn.cursor(binary=False) as cur:
                cur.execute("SELECT veh_emb FROM sightings WHERE id = %s", (sighting_id,))
                text_value = cur.fetchone()["veh_emb"]

            checks = {
                "binary result is np.ndarray": isinstance(binary_value, np.ndarray),
                "dtype is float32": getattr(binary_value, "dtype", None) == np.float32,
                "length correct": len(binary_value) == EMBEDDING_DIM,
                "exactly equals inserted vector": np.array_equal(
                    np.asarray(binary_value, dtype=np.float32), original
                ),
                "binary matches text path": np.array_equal(
                    np.asarray(binary_value, dtype=np.float32),
                    np.asarray(text_value, dtype=np.float32),
                ),
            }

            for label, ok in checks.items():
                if not ok:
                    failures.append(f"{sighting_id}: {label}")

            status = "PASS" if all(checks.values()) else "FAIL"
            print(
                f"  {status}  first={float(binary_value[0]):+.6f} "
                f"last={float(binary_value[-1]):+.6f} "
                f"norm={float(np.linalg.norm(np.asarray(binary_value, dtype=np.float32))):.6f}"
            )

        # NULL rider_emb must survive as None, not become an empty array.
        with conn.cursor(binary=True) as cur:
            cur.execute(
                "SELECT rider_emb FROM sightings WHERE crop_path = %s LIMIT 1", (TAG,)
            )
            if cur.fetchone()["rider_emb"] is not None:
                failures.append("NULL rider_emb did not come back as None")

        with conn.cursor() as cur:
            cur.execute("DELETE FROM sightings WHERE crop_path = %s", (TAG,))
        conn.commit()

    print()
    if failures:
        print(f"{len(failures)} FAILURE(S):")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("ALL CHECKS PASSED — binary loader is byte-exact")
    return 0


if __name__ == "__main__":
    sys.exit(main())
