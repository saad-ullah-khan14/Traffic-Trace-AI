r"""End-to-end smoke test: drive the real API exactly as the demo does.

preflight.py answers "is this machine ready?". This answers "does the whole
flow still work right now?" - every endpoint, every guard, the WebSocket, and
a full A -> B -> C journey, through real HTTP against a running server.

It is destructive: it resets the demo data twice. Run it BEFORE the phones are
set up, never during. It leaves the database clean.

    Start the API first, then:
        cd api
        .\.venv\Scripts\python.exe -m scripts.smoke_demo

Needs three JPEGs to push through the pipeline. By default it uses the sample
frames in tools/test_recordings; point FRAMES_DIR at a folder of your own if you
would rather test with real street photos.
"""

import json
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

import requests

from pathlib import Path

from app.core.config import settings  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
BASE = "http://127.0.0.1:8000"
FRAMES_DIR = REPO / "tools" / "test_recordings" / "cam-A"
TOKENS_PATH = REPO / "tools" / "tokens.json"

results = []


def check(label, ok, detail=""):
    results.append((label, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  -  {detail}" if detail else ""))
    return ok


def section(name):
    print(f"\n{name}\n" + "-" * 72)


PIN = settings.OFFICER_PIN
PIN_HDR = {"X-Officer-Pin": PIN}

FRAMES = sorted(p for p in FRAMES_DIR.glob("*.jpg"))
if not FRAMES:
    sys.exit(f"no .jpg frames in {FRAMES_DIR} - point FRAMES_DIR at some street photos")
TEMP_CAMERA_NAME = "SMOKE TEST temp camera"

# ---------------------------------------------------------------- websocket
ws_events = []
ws_error = []


def ws_listen(stop_after=60):
    try:
        from websockets.sync.client import connect

        with connect("ws://127.0.0.1:8000/ws/live", open_timeout=10) as sock:
            deadline = time.time() + stop_after
            while time.time() < deadline:
                try:
                    msg = sock.recv(timeout=2)
                except TimeoutError:
                    continue
                except Exception:
                    break
                try:
                    ws_events.append(json.loads(msg))
                except Exception:
                    pass
    except Exception as exc:  # noqa: BLE001
        ws_error.append(f"{type(exc).__name__}: {exc}")


def post_frame(token, path, ts):
    with open(path, "rb") as fh:
        return requests.post(
            f"{BASE}/api/frames",
            headers={"X-Camera-Token": token},
            files={"frame": fh},
            data={"ts": ts},
            timeout=30,
        )


def drain(seconds=12, expect=0):
    """Wait for the worker to go genuinely idle.

    An empty queue is not the same as finished: the last job has already been
    taken off the queue and is still running inference, and `processed` only
    increments afterwards. Reading the counter then reports a frame missing that
    is simply not done yet - a false failure that sends someone hunting a bug
    that is not there.

    Waiting for the count to "stop moving" has the same hole: two reads a second
    apart both see the old value while inference is still running. So wait for a
    specific total instead - `expect` is what processed must reach.
    """
    deadline = time.time() + seconds
    while time.time() < deadline:
        st = requests.get(f"{BASE}/api/frames/stats", timeout=5).json()
        if st["queued"] == 0 and st["processed"] >= expect:
            return st
        time.sleep(1.0)
    return requests.get(f"{BASE}/api/frames/stats", timeout=5).json()


print("\nTraffic_Trace - full demo-path audit")
print("=" * 72)

# =========================================================== 1. health / config
section("1. Health and configuration")
h = requests.get(f"{BASE}/api/health", timeout=15).json()
check("GET /api/health -> ok", h.get("status") == "ok", json.dumps(h.get("db", {}))[:70])
check("real pipeline loaded, not the stub", h["pipeline"]["real"] is True, h["pipeline"]["status"])
check("OFFICER_PIN is set", bool(PIN), f"{len(PIN)} chars" if PIN else "MISSING")
if PIN == "4321":
    print("        note: this is the PIN printed in docs/RUNBOOK.md. Fine for a demo,")
    print("        but change both if the laptop is ever left unattended.")

# Counters are cumulative for the life of the process, so everything below
# compares against this snapshot rather than against zero.
BASELINE = requests.get(f"{BASE}/api/frames/stats", timeout=10).json()

# =========================================================== 2. auth guards
section("2. Auth guards")
r = requests.post(f"{BASE}/api/frames", files={"frame": ("x.jpg", b"x")}, timeout=10)
check("POST /api/frames with no token -> 401", r.status_code == 401, f"got {r.status_code}")
r = requests.post(f"{BASE}/api/frames", headers={"X-Camera-Token": "not-a-real-token"},
                  files={"frame": ("x.jpg", b"x")}, timeout=10)
check("POST /api/frames with a bad token -> 401", r.status_code == 401, f"got {r.status_code}")
r = requests.post(f"{BASE}/api/admin/reset", timeout=10)
check("POST /api/admin/reset with no PIN -> 401", r.status_code == 401, f"got {r.status_code}")
r = requests.post(f"{BASE}/api/admin/reset", headers={"X-Officer-Pin": "0000"}, timeout=10)
check("POST /api/admin/reset with a wrong PIN -> 401", r.status_code == 401, f"got {r.status_code}")
r = requests.post(f"{BASE}/api/admin/verify-pin", headers=PIN_HDR, timeout=10)
check("POST /api/admin/verify-pin with the right PIN -> 200", r.status_code == 200, f"got {r.status_code}")

# =========================================================== 3. reset
section("3. Reset to a clean state")
r = requests.post(f"{BASE}/api/admin/reset", headers=PIN_HDR, timeout=30)
check("POST /api/admin/reset -> 200", r.status_code == 200, json.dumps(r.json())[:90])
inc = requests.get(f"{BASE}/api/incidents", timeout=10).json()
check("incident feed is empty after reset", inc == [], f"{len(inc)} incidents")

# =========================================================== 4. cameras
section("4. Cameras")
cams = requests.get(f"{BASE}/api/cameras", timeout=10).json()
check("GET /api/cameras -> exactly 3, no strays", len(cams) == 3, ", ".join(c["name"] for c in cams))
check("every camera has coordinates",
      all(c.get("lat") and c.get("lng") for c in cams),
      "; ".join(f"{c['lat']:.4f},{c['lng']:.4f}" for c in cams))

tokens = json.load(open(TOKENS_PATH, encoding="utf-8-sig"))  # BOM-tolerant
check("tools/tokens.json has 3 camera tokens", len(tokens) == 3, ", ".join(tokens))

r = requests.post(f"{BASE}/api/cameras", json={"name": TEMP_CAMERA_NAME,
                                               "lat": 25.01, "lng": 67.04, "heading": 90}, timeout=10)
check("POST /api/cameras -> 201 with a token", r.status_code == 201 and "token" in r.json(),
      f"got {r.status_code}")
temp_cam = r.json() if r.status_code == 201 else None
if temp_cam:
    r2 = requests.post(f"{BASE}/api/cameras/claim", json={"token": temp_cam["token"]}, timeout=10)
    check("POST /api/cameras/claim with that token -> 200", r2.status_code == 200, f"got {r2.status_code}")
    r3 = requests.patch(f"{BASE}/api/cameras/me/location",
                        headers={"X-Camera-Token": temp_cam["token"]},
                        json={"lat": 25.02, "lng": 67.05}, timeout=10)
    check("PATCH /api/cameras/me/location -> 200", r3.status_code == 200, f"got {r3.status_code}")

# =========================================================== 5. the demo run
section("5. The A -> B -> C demo path, through real HTTP")

listener = threading.Thread(target=ws_listen, args=(75,), daemon=True)
listener.start()
time.sleep(2)
check("WebSocket /ws/live connected", not ws_error, ws_error[0] if ws_error else "listening")

T = datetime.now(timezone.utc)


def iso(delta_s):
    return (T + timedelta(seconds=delta_s)).strftime("%Y-%m-%dT%H:%M:%SZ")


# cam-A: the violation. cam-B and cam-C: the same street scene later, far enough
# apart in time to clear the reachability gate (52 s and 96 s minimums).
plan = [
    ("cam-A", FRAMES[0], iso(-600), "vehicle at camera A"),
    ("cam-B", FRAMES[min(1, len(FRAMES) - 1)], iso(-400), "vehicle at camera B"),
    ("cam-C", FRAMES[min(2, len(FRAMES) - 1)], iso(-150), "vehicle at camera C"),
]

accepted = 0
for cam, path, ts, why in plan:
    resp = post_frame(tokens[cam], path, ts)
    ok = resp.status_code == 202 and resp.json().get("accepted")
    accepted += 1 if ok else 0
    check(f"POST /api/frames  {why} -> 202 accepted", ok,
          f"{resp.status_code} {json.dumps(resp.json())[:60]}")

stats = drain(90, expect=BASELINE["processed"] + accepted)
check("worker drained the queue", stats["queued"] == 0, json.dumps(stats))
check("every frame we sent was processed",
      stats["processed"] - BASELINE["processed"] >= accepted,
      f"+{stats['processed'] - BASELINE['processed']} processed for {accepted} sent")
check("nothing dropped at this light load",
      stats["dropped"] == BASELINE["dropped"],
      f"+{stats['dropped'] - BASELINE['dropped']} dropped")
check("no frames failed in the worker",
      stats["failed"] == BASELINE["failed"],
      f"+{stats['failed'] - BASELINE['failed']} failed")

# =========================================================== 6. incidents
section("6. Incident feed and review screen")
feed = requests.get(f"{BASE}/api/incidents", timeout=15).json()
check("GET /api/incidents returns the violations", len(feed) > 0, f"{len(feed)} incidents")

if not feed:
    print("\n  Those frames contained no violation, so there is nothing to review.")
    print(f"  Point FRAMES_DIR at photos with a helmetless rider (currently {FRAMES_DIR}).")
    sys.exit(1)

item = feed[0]
check("feed item has violation, camera, crop_url, match_count",
      all(k in item for k in ("violation", "camera", "crop_url", "match_count")),
      f"violation={item.get('violation')} matches={item.get('match_count')}")

crop = requests.get(f"{BASE}{item['crop_url']}", timeout=10)
check("GET the crop_url off /evidence -> 200 image", crop.status_code == 200 and len(crop.content) > 500,
      f"{crop.status_code}, {len(crop.content)} bytes")

# The incident that actually collected candidates is the one worth reviewing.
detail = None
for cand in feed:
    d = requests.get(f"{BASE}/api/incidents/{cand['id']}", timeout=15).json()
    if d.get("matches"):
        detail = d
        break
if detail is None:
    detail = requests.get(f"{BASE}/api/incidents/{feed[0]['id']}", timeout=15).json()

check("GET /api/incidents/{id} has sighting + camera + attrs",
      detail.get("sighting", {}).get("camera", {}).get("name") is not None,
      detail.get("sighting", {}).get("camera", {}).get("name", "MISSING"))
check("review screen has ranked candidates", len(detail.get("matches", [])) > 0,
      f"{len(detail.get('matches', []))} candidates")

if detail.get("matches"):
    top = detail["matches"][0]
    bd = top.get("breakdown") or {}
    check("top candidate carries a 4-signal breakdown",
          set(bd) >= {"vehicle", "rider", "attributes", "space_time"},
          f"score={top['score']:.4f} {bd}")
    check("candidates are sorted by score, best first",
          all(detail["matches"][i]["score"] >= detail["matches"][i + 1]["score"]
              for i in range(len(detail["matches"]) - 1)),
          f"{[round(m['score'], 3) for m in detail['matches'][:5]]}")
    check("no candidate is from the incident's own camera",
          all(m["sighting"]["camera"]["id"] != detail["sighting"]["camera"]["id"]
              for m in detail["matches"]),
          "same-camera exclusion holds on live data")

# =========================================================== 7. confirm + journey
section("7. Confirm a match, then the journey")
if detail.get("matches"):
    mid = detail["matches"][0]["id"]
    r = requests.post(f"{BASE}/api/matches/{mid}/decision", json={"decision": "confirm"}, timeout=15)
    check("POST /api/matches/{id}/decision without a PIN -> 401", r.status_code == 401, f"got {r.status_code}")
    r = requests.post(f"{BASE}/api/matches/{mid}/decision", headers=PIN_HDR,
                      json={"decision": "confirm"}, timeout=20)
    check("POST /api/matches/{id}/decision confirm -> 200", r.status_code == 200,
          json.dumps(r.json())[:80] if r.status_code < 500 else str(r.status_code))
    r = requests.post(f"{BASE}/api/matches/{mid}/decision", headers=PIN_HDR,
                      json={"decision": "nonsense"}, timeout=10)
    check("an invalid decision value -> 400", r.status_code == 400, f"got {r.status_code}")

    time.sleep(2)
    j = requests.get(f"{BASE}/api/journeys/{detail['id']}", timeout=15)
    ok = j.status_code == 200
    jd = j.json() if ok else {}
    check("GET /api/journeys/{incident_id} -> 200", ok, f"got {j.status_code}")
    check("journey has at least 2 stops", len(jd.get("stops", [])) >= 2,
          f"{len(jd.get('stops', []))} stop(s), {jd.get('total_distance_km')} km")
    drawable = [s for s in jd.get("stops", []) if s.get("lat") is not None and s.get("lon") is not None]
    check("every stop is map-drawable (lat + lon present)",
          len(drawable) == len(jd.get("stops", [])) and len(drawable) >= 2,
          f"{len(drawable)}/{len(jd.get('stops', []))} positioned")
    check("every stop carries a crop for the map popup",
          all(s.get("crop_url") for s in jd.get("stops", [])),
          f"{sum(1 for s in jd.get('stops', []) if s.get('crop_url'))} with crops")

# =========================================================== 8. websocket events
section("8. Live WebSocket events")
time.sleep(3)
kinds = {}
for e in ws_events:
    kinds[e.get("type")] = kinds.get(e.get("type"), 0) + 1
check("WebSocket delivered events at all", len(ws_events) > 0, f"{len(ws_events)} messages: {kinds}")
check("'sighting' events fired", kinds.get("sighting", 0) > 0, f"{kinds.get('sighting', 0)}")
check("'incident' events fired", kinds.get("incident", 0) > 0, f"{kinds.get('incident', 0)}")
check("'match_suggestion' events fired", kinds.get("match_suggestion", 0) > 0,
      f"{kinds.get('match_suggestion', 0)}")
check("'journey_update' fired on confirm", kinds.get("journey_update", 0) > 0,
      f"{kinds.get('journey_update', 0)}")

# =========================================================== 9. error paths
section("9. Error handling")
r = requests.get(f"{BASE}/api/incidents/00000000-0000-0000-0000-000000000000", timeout=10)
check("unknown incident id -> 404", r.status_code == 404, f"got {r.status_code}")
r = requests.get(f"{BASE}/api/incidents/not-a-uuid", timeout=10)
check("malformed uuid -> 422", r.status_code == 422, f"got {r.status_code}")
r = requests.get(f"{BASE}/api/journeys/00000000-0000-0000-0000-000000000000", timeout=10)
check("journey for an unknown incident -> 404 or empty",
      r.status_code in (200, 404), f"got {r.status_code}")
r = requests.post(f"{BASE}/api/frames", headers={"X-Camera-Token": tokens["cam-A"]},
                  files={"frame": ("empty.jpg", b"")}, timeout=10)
check("empty frame body -> 400", r.status_code == 400, f"got {r.status_code}")
r = requests.post(f"{BASE}/api/frames", headers={"X-Camera-Token": tokens["cam-A"]},
                  files={"frame": ("junk.jpg", b"this is not a jpeg at all")}, timeout=10)
check("a non-JPEG body is accepted then survived by the worker",
      r.status_code == 202, f"got {r.status_code}")
time.sleep(4)
st = requests.get(f"{BASE}/api/frames/stats", timeout=10).json()
check("the garbage frame did not crash the worker",
      st["failed"] == BASELINE["failed"], json.dumps(st))

# =========================================================== 10. cleanup
section("10. Cleanup")
r = requests.post(f"{BASE}/api/admin/reset", headers=PIN_HDR, timeout=30)
check("reset again, leaving the database clean for tomorrow", r.status_code == 200,
      json.dumps(r.json())[:90])

# The reset keeps cameras on purpose (their tokens are typed into phones), so
# the registration test's camera has to be removed here. A fourth camera would
# change the reachability geometry and put a stray pin on the demo map.
from app.db.session import get_connection  # noqa: E402

with get_connection() as conn, conn.cursor() as cur:
    cur.execute("DELETE FROM cameras WHERE name = %s", (TEMP_CAMERA_NAME,))
    removed = cur.rowcount
    cur.execute("SELECT count(*) AS n FROM cameras")
    remaining = cur.fetchone()["n"]
check("the test camera was removed, leaving the 3 demo cameras",
      remaining == 3, f"removed {removed}, {remaining} cameras remain")

# =========================================================== report
print("\n" + "=" * 72)
failed = [(l, d) for l, ok, d in results if not ok]
print(f"  {len(results) - len(failed)} passed | {len(failed)} failed")
if failed:
    print("\n  FAILURES:")
    for label, detail in failed:
        print(f"    - {label}  ({detail})")
sys.exit(1 if failed else 0)
