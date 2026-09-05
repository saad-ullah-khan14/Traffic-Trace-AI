r"""Regression test for the same-camera space-time exploit.

The bug: pipeline._space_time_score computes a required speed from
distance / time. For a candidate at the SAME camera the distance is 0, so the
required speed is 0, so it returns a perfect 1.0 on the heaviest-weighted
signal (0.35) at any time gap. Measured consequences before the fix:

  * an unrelated bike that passed the same camera two minutes later outscored
    the genuine cross-camera match, and could push it off the top-20 review
    screen entirely — that screen is the demo;
  * the minimum achievable same-camera score was 0.609, above the 0.6 watchlist
    threshold, so every open incident alerted on every passing vehicle.

Fixed in two layers, and this test asserts both:
  * ours — same-camera pairs never reach the scorer at all:
        app/services/geo.py build_gate   — the SQL gate excludes them
        app/services/watchlist.py        — the watchlist skips them
  * upstream (pipeline_v9, integrated 29 Aug 2026) — _space_time_score now
        returns None for distance_m == 0, so the signal is treated as missing
        and its weight is redistributed, instead of scoring a free 1.0.

Both layers are kept. Ours is what the demo relies on; the upstream one is the
root fix, and this test fails loudly if either regresses. Uses the real seeded
camera geometry and the real pipeline.score_candidates. Needs no server and
writes nothing.

    cd api
    .\.venv\Scripts\python.exe -m scripts.test_same_camera_fix
"""

import sys
from datetime import datetime, timedelta, timezone

import numpy as np

from app.core.constants import EMBEDDING_DIM
from app.db.queries import cameras as cameras_q
from app.db.session import get_connection
from app.services.geo import build_gate, haversine_meters
from app.services.pipeline_client import score_candidates

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))
    if not ok:
        failures.append(label)


def unit(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(EMBEDDING_DIM).astype(np.float32)
    return v / np.linalg.norm(v)


def at_cosine(base: np.ndarray, target: float, seed: int) -> list[float]:
    """A unit vector whose cosine with `base` is exactly `target`.

    Random vectors are near-orthogonal, which is nothing like reality: measured
    in Phase 7, CLIP similarity between ANY two vehicle crops sits in a narrow
    0.84-0.93 band. Testing against a 0.00-similarity "different vehicle" would
    make the bug look harmless when it is not.
    """
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal(EMBEDDING_DIM).astype(np.float32)
    perp = noise - np.dot(noise, base) * base
    perp /= np.linalg.norm(perp)
    v = target * base + np.sqrt(1.0 - target**2) * perp
    return (v / np.linalg.norm(v)).tolist()


def histogram(overlap: float, seed: int = 0) -> list[float]:
    """An 8-bucket histogram intersecting the reference below by `overlap`."""
    share = overlap / 2.0
    rest = (1.0 - overlap) / 2.0
    return [share, share, rest, rest, 0.0, 0.0, 0.0, 0.0]


def main() -> int:
    print("\nsame-camera exploit — regression test\n" + "=" * 46)

    with get_connection() as conn:
        cameras = cameras_q.list_cameras(conn)

    if len(cameras) < 2:
        print("need at least 2 seeded cameras — run scripts.seed_cameras")
        return 1

    origin, other = cameras[0], cameras[1]

    # --- 1. the SQL gate must not offer same-camera candidates --------------
    print("\n[1] space-time gate")
    camera_ids, min_gaps = build_gate(
        origin["lat"], origin["lng"], cameras, origin_camera_id=origin["id"]
    )
    check(
        "origin camera excluded from the gate",
        origin["id"] not in camera_ids,
        f"{len(camera_ids)} of {len(cameras)} cameras gated",
    )
    check(
        "other cameras still gated, with a real minimum gap",
        len(camera_ids) == len(cameras) - 1 and all(g > 0 for g in min_gaps),
        f"min gaps {[round(g) for g in min_gaps]} s",
    )

    # --- 2. a real cross-camera match must outrank same-camera junk ---------
    print("\n[2] ranking, through the real scorer")
    now = datetime.now(timezone.utc)
    distance = haversine_meters(origin["lat"], origin["lng"], other["lat"], other["lng"])

    # Derive the gap from the actual spacing rather than hardcoding one. Camera
    # positions move: the /camera page lets a phone report its own location, so
    # a field test relocates them, and a fixed 150 s that was comfortable at
    # 1.37 km is a 53 km/h dash at 2.4 km. The test would then fail for a reason
    # that has nothing to do with what it is testing.
    #
    # 25 km/h is ordinary city riding and is what the demo actually produces.
    plausible_gap = max(60.0, (distance / 1000.0) / 25.0 * 3600.0)

    incident_emb = unit(1)  # ndarray; the payloads below carry lists
    incident = {
        "sighting_id": "incident",
        "camera_id": str(origin["id"]),
        "ts": now.isoformat(),
        "vehicle_type": "motorcycle",
        "veh_emb": incident_emb.tolist(),
        "rider_emb": None,
        "attrs": {"color": "red", "color_histogram": [0.5, 0.5, 0, 0, 0, 0, 0, 0]},
    }

    def candidate(name, cam, dist_m, gap_s, emb, hist):
        return {
            "sighting_id": name,
            "camera_id": str(cam["id"]),
            "ts": (now - timedelta(seconds=gap_s)).isoformat(),
            "vehicle_type": "motorcycle",
            "veh_emb": emb,
            "rider_emb": None,
            "attrs": {"color": "red", "color_histogram": hist},
            "visual_score": 0.9,
            "distance_m": dist_m,
            "time_gap_seconds": gap_s,
        }

    # Realistic values, taken from what this system actually measures:
    # a genuine match at the other camera — strong colour agreement, plausible
    # travel time, and a CLIP similarity typical of the same vehicle.
    # 150 s for 1.37 km is ~33 km/h — ordinary city riding, and exactly the
    # timing the A->B->C demo produces. Note this is the WORST case for the true
    # match: a shorter gap means a higher required speed, which scores LOWER on
    # space-time. The signal rewards a vehicle for taking its time.
    true_match = candidate(
        "TRUE-cross-camera", other, distance, plausible_gap,
        at_cosine(incident_emb, 0.90, seed=11), histogram(0.70),
    )
    # An unrelated bike that merely passed the origin camera. Its CLIP score is
    # HIGHER than the true match's — that is not a contrived case, it is exactly
    # what Phase 7 measured on real photos — and its colour agrees far less.
    junk_same_camera = candidate(
        "junk-same-camera", origin, 0.0, plausible_gap * 0.8,
        at_cosine(incident_emb, 0.91, seed=12), histogram(0.35),
    )

    both = score_candidates(incident, [true_match, junk_same_camera])
    if not both:
        print("  score_candidates returned nothing — is pipeline/ present?")
        return 1

    by_id = {r["sighting_id"]: r for r in both}
    true_score = by_id["TRUE-cross-camera"]["score"]
    junk_score = by_id["junk-same-camera"]["score"]

    print(f"       geometry: {distance / 1000:.2f} km apart, testing a {plausible_gap:.0f}s gap "
          f"(~25 km/h)")
    print(f"       true cross-camera match : {true_score:.4f}  {by_id['TRUE-cross-camera']['breakdown']}")
    print(f"       same-camera junk        : {junk_score:.4f}  {by_id['junk-same-camera']['breakdown']}")

    check(
        "same-camera pair no longer gets a free perfect space_time",
        by_id["junk-same-camera"]["breakdown"]["space_time"] != 1.0,
        "upstream returns None for distance 0; its weight is redistributed",
    )
    check(
        "the true cross-camera match now outranks same-camera junk",
        true_score > junk_score,
        f"true {true_score:.4f} > junk {junk_score:.4f} "
        f"(+{true_score - junk_score:.4f})",
    )
    check(
        "and the gate never returns same-camera rows anyway",
        origin["id"] not in camera_ids,
        "belt and braces — the demo does not depend on the upstream fix",
    )

    # --- 3. the watchlist threshold is only safe once same-camera is gone ---
    print("\n[3] watchlist threshold")
    # The floor: the least similar pair CLIP can realistically produce (0.84,
    # the bottom of the measured band) with no colour agreement at all.
    worst_same_camera = candidate(
        "worst-case-same-camera", origin, 0.0, 3600,
        at_cosine(incident_emb, 0.84, seed=13), histogram(0.0),
    )
    worst = score_candidates(incident, [worst_same_camera])[0]["score"]
    check(
        "worst realistic same-camera pair now falls below the 0.6 threshold",
        worst < 0.6,
        f"floor is {worst:.4f} — was 0.609 before the fix, alerting on everything",
    )

    src = (__import__("pathlib").Path(__file__).resolve().parents[1]
           / "app" / "services" / "watchlist.py").read_text(encoding="utf-8")
    check(
        "watchlist skips same-camera incidents",
        'incident["camera_id"] == sighting["camera_id"]' in src,
        "guard present in check_sighting",
    )

    print("\n" + "=" * 46)
    if failures:
        print(f"  {len(failures)} FAILED: {failures}")
        return 1
    print("  all checks passed — closed on both sides: the gate excludes")
    print("  same-camera rows, and _space_time_score no longer rewards them")
    return 0


if __name__ == "__main__":
    sys.exit(main())
