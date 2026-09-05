r"""Seed the three demo cameras.

⚠️ PLACEHOLDER COORDINATES, centred on the GPS fix the phone actually reported
during the Phase 6 test (Karachi). Roughly 1-2 km apart, so the reachability
maths has sensible distances. Replace with the real demo locations before
testing outdoors — the space-time gate's minimum travel times come from these,
and the offline tile cache is centred on the same point.

Idempotent: re-running updates positions instead of creating duplicates.

    cd api
    .\.venv\Scripts\python.exe -m scripts.seed_cameras
"""

import json
import secrets
from pathlib import Path

from app.db.queries import cameras as cameras_q
from app.db.session import get_connection
from app.services.geo import haversine_meters, min_travel_seconds

DEMO_CAMERAS = [
    {"name": "Camera 1 — Shahrah-e-Faisal", "lat": 25.0110, "lng": 67.0403, "heading": 135.0},
    {"name": "Camera 2 — Tipu Sultan Rd",   "lat": 25.0205, "lng": 67.0490, "heading": 45.0},
    {"name": "Camera 3 — Karsaz",           "lat": 25.0020, "lng": 67.0530, "heading": 270.0},
]


def main() -> None:
    with get_connection() as conn:
        existing = {c["name"]: c for c in cameras_q.list_cameras(conn)}

        for spec in DEMO_CAMERAS:
            if spec["name"] in existing:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE cameras SET lat=%s, lng=%s, heading=%s WHERE name=%s",
                        (spec["lat"], spec["lng"], spec["heading"], spec["name"]),
                    )
                print(f"updated  {spec['name']}")
            else:
                camera = cameras_q.insert_camera(
                    conn,
                    name=spec["name"],
                    lat=spec["lat"],
                    lng=spec["lng"],
                    heading=spec["heading"],
                    token=secrets.token_urlsafe(24),
                )
                print(f"created  {camera['name']}  token={camera['token']}")

        cameras = cameras_q.list_cameras(conn)

        # tools/replay.py needs the tokens and has no DB access. Short keys
        # (cam-A/B/C) rather than the display names, because they double as
        # the recording folder names.
        #
        # ORDER BY name, NOT created_at. start_demo.ps1 writes this same file
        # ordered by name, and the two disagreed: created_at order on this
        # machine put Camera 3 first, so seed_cameras wrote cam-A = Camera 3
        # while start_demo wrote cam-A = Camera 1. Whichever ran last decided
        # what cam-A meant, and replay.py would then submit the camera-A
        # recording as a different camera entirely - wrong geometry, wrong
        # route, and not one error message anywhere. Name order is stable and
        # is what a human reading "Camera 1" expects.
        with conn.cursor() as cur:
            cur.execute("SELECT token FROM cameras ORDER BY name")
            tokens = {
                f"cam-{chr(65 + i)}": row["token"] for i, row in enumerate(cur.fetchall())
            }
        tokens_path = Path(__file__).resolve().parents[2] / "tools" / "tokens.json"
        tokens_path.write_text(json.dumps(tokens, indent=2), encoding="utf-8")
        print(f"wrote {tokens_path} ({len(tokens)} tokens) — gitignored")

    print(f"\n{len(cameras)} cameras in the database\n")
    print("Pairwise distances and the minimum travel time the gate will enforce:")
    for i, a in enumerate(cameras):
        for b in cameras[i + 1:]:
            metres = haversine_meters(a["lat"], a["lng"], b["lat"], b["lng"])
            print(
                f"  {a['name']:<24} -> {b['name']:<24} "
                f"{metres / 1000:6.2f} km   min gap {min_travel_seconds(metres):6.1f}s"
            )


if __name__ == "__main__":
    main()
