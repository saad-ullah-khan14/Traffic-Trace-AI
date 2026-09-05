r"""When does a violation open a NEW case, and when do two cases become one?

This is the most intricate rule in the product and the easiest to break by
accident, so it gets its own test.

    one rider, one offence, one card - once the officer has said so

    - several frames of one pass at one camera        -> one case (time-based)
    - the same rider at other cameras                 -> a case each, at first
    - the officer confirms they are the same vehicle  -> folded into one card
    - a different rider                               -> always its own case

Grouping is deliberately NOT attempted from a similarity score. Measured on real
footage the same rider scores 0.52-0.55 across cameras while six different riders
scored 0.69-0.75 — the same vehicle scores LOWER than different ones, so there is
no threshold to find. Only the officer knows, so only the officer merges.

Needs the API running. Destructive: resets the demo data. Leaves it clean.

    cd api
    .\.venv\Scripts\python.exe -m scripts.test_case_grouping
"""

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from app.core.config import settings

REPO = Path(__file__).resolve().parents[2]
BASE = "http://127.0.0.1:8000"
TOKENS_PATH = REPO / "tools" / "tokens.json"

# A helmetless rider whose plate cannot be read - the case this product is for.
FRAME = REPO / "tools" / "test_recordings" / "violation.jpg"
# A DIFFERENT helmetless rider, for checking that merging never swallows one.
OTHER = REPO / "tools" / "test_recordings" / "other_rider.jpg"

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  -  {detail}" if detail else ""))
    if not ok:
        failures.append(label)


def post(cam: str, ts: str, frame: Path = FRAME):
    with open(frame, "rb") as fh:
        return requests.post(
            f"{BASE}/api/frames",
            headers={"X-Camera-Token": TOKENS[cam]},
            files={"frame": fh},
            data={"ts": ts},
            timeout=90,
        )


def processed_count() -> int:
    return requests.get(f"{BASE}/api/frames/stats", timeout=5).json()["processed"]


def wait_for(target: int) -> None:
    """Wait until the worker has processed `target` frames in total.

    Counting, not waiting for quiet. "Queue empty and the counter has not moved"
    is indistinguishable from "the last frame left the queue and is still running
    inference", which takes about a second — so a quiet-based wait returns early
    and the caller reads the database before the work has landed. That produced
    two test failures that looked exactly like product bugs and were not.
    """
    for _ in range(180):
        if processed_count() >= target:
            return
        time.sleep(1)
    raise AssertionError(f"worker never reached {target} processed frames")


def feed() -> list[dict]:
    return requests.get(f"{BASE}/api/incidents", timeout=15).json()


def send(cam: str, ts: str, frame: Path = FRAME) -> None:
    target = processed_count() + 1
    post(cam, ts, frame)
    wait_for(target)


def main() -> int:
    global TOKENS

    for frame in (FRAME, OTHER):
        if not frame.exists():
            print(f"missing test frame: {frame}")
            return 1

    TOKENS = json.load(open(TOKENS_PATH, encoding="utf-8-sig"))
    pin = {"X-Officer-Pin": settings.OFFICER_PIN}

    print("\ncase grouping - one rider, one offence, one card")
    print("=" * 74)

    requests.post(f"{BASE}/api/admin/reset", headers=pin, timeout=60)
    t0 = datetime.now(timezone.utc) - timedelta(seconds=900)

    def at(offset: int) -> str:
        return (t0 + timedelta(seconds=offset)).strftime("%Y-%m-%dT%H:%M:%SZ")

    # --- 1. one pass is one case, however many frames caught it ----------
    print("\n[1] one pass at camera 1, five frames of it")
    target = processed_count() + 5
    for i in range(5):
        post("cam-A", at(i))
    wait_for(target)
    check("five flagged frames make ONE case", len(feed()) == 1, f"{len(feed())} cases")

    # --- 2. other cameras open their own, for now ------------------------
    print("\n[2] the same rider reaches camera 2, then camera 3")
    send("cam-B", at(200))
    send("cam-C", at(450))
    cases = feed()
    check(
        "each camera opens a case - nothing is guessed away",
        len(cases) == 3,
        f"{len(cases)} cases",
    )

    # --- 3. and they hold each other as candidates -----------------------
    first = sorted(cases, key=lambda i: i["created_at"])[0]
    detail = requests.get(f"{BASE}/api/incidents/{first['id']}", timeout=20).json()
    other_cameras = {m["sighting"]["camera"]["name"] for m in detail["matches"]}
    print(f"\n[3] the camera 1 case offers {len(detail['matches'])} candidates")
    check(
        "both later cameras appear as candidates on it",
        len(other_cameras) == 2,
        ", ".join(sorted(c[:26] for c in other_cameras)),
    )
    check(
        "no candidate is from the case's own camera",
        detail["sighting"]["camera"]["name"] not in other_cameras,
        "same-camera exclusion holds",
    )

    # --- 4. the officer confirms, and the duplicate card folds away ------
    print("\n[4] the officer confirms one candidate as the same vehicle")
    confirmed_cameras = set()
    for match in sorted(detail["matches"], key=lambda m: -m["score"]):
        camera = match["sighting"]["camera"]["name"]
        if camera in confirmed_cameras:
            continue
        before = len(feed())
        requests.post(
            f"{BASE}/api/matches/{match['id']}/decision",
            headers=pin, json={"decision": "confirm"}, timeout=30,
        )
        time.sleep(1.5)
        after = len(feed())
        print(f"    confirmed {camera[:26]:<28} {before} cards -> {after}")
        check(f"confirming {camera[7:9]} removed a duplicate card", after == before - 1,
              f"{before} -> {after}")
        confirmed_cameras.add(camera)

    check("one offender now shows as one card", len(feed()) == 1, f"{len(feed())} cases")

    # --- 5. and the route is the whole journey ---------------------------
    print("\n[5] the route")
    response = requests.get(f"{BASE}/api/journeys/{first['id']}", timeout=20)
    stops = response.json().get("stops", []) if response.status_code == 200 else []
    for i, stop in enumerate(stops, 1):
        print(f"    {i}. {stop.get('camera_name')}")
    check("the route reaches all three cameras", len(stops) == 3, f"{len(stops)} stops")
    check(
        "each stop is a different camera",
        len({s.get("camera_name") for s in stops}) == len(stops),
        f"{len({s.get('camera_name') for s in stops})} distinct",
    )

    # --- 6. a different rider is never swallowed -------------------------
    print("\n[6] a DIFFERENT helmetless rider arrives")
    before = len(feed())
    send("cam-B", at(2400), frame=OTHER)
    after = len(feed())
    check(
        "a different offender always gets their own case",
        after > before,
        f"{before} -> {after} cases",
    )

    requests.post(f"{BASE}/api/admin/reset", headers=pin, timeout=60)

    print("\n" + "=" * 74)
    if failures:
        print(f"  {len(failures)} FAILED: {failures}")
        return 1
    print("  the officer decides what is one offender, and the feed follows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
