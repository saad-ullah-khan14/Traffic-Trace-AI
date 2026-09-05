r"""Real production-path benchmark.

Unlike labelset/benchmark.py (which only tests a raw embedder OR reads a
stale baseline_score from labels.json), THIS script calls the actual
production functions as they run live:

    pipeline.fingerprint.fingerprint(crop)   -> veh_emb, rider_emb=None, attrs
    pipeline.matcher.score_candidates(...)   -> fused score with CURRENT weights

Run from the repo root (D:\Traffic_Trace\Traffic_Trace):

    python real_benchmark.py

Requires: labelset/labels.json, labelset/crops/*, and pipeline/ importable
(run from repo root so `import pipeline.fingerprint` works).

HONESTY NOTE printed at the end: rider_emb is None for every crop here,
because labelset/crops are single union images (vehicle+rider together),
not separate rider-only crops. So WEIGHT_RIDER (0.25) is NOT exercised by
this test — its weight gets redistributed to vehicle/attributes/space_time
by score_candidates()'s "available signals" logic. Same for distance_m /
time_gap_seconds: if labels.json doesn't carry them, WEIGHT_SPACE_TIME
(0.25) is also redistributed. This script prints exactly which signals
were actually exercised, every run, so nobody can accidentally repeat the
"100% confirmed" mistake from before.
"""

import json
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
# Muhammad's repo layout: labelset/labels.json, labelset/crops/
# (your own project used a nested labelset/labelset/ — adjust back if needed)
LABELSET = HERE / "labelset"
CROPS = LABELSET / "crops"

sys.path.insert(0, str(HERE))

from pipeline.fingerprint import fingerprint  # noqa: E402
from pipeline.matcher import (  # noqa: E402
    WEIGHT_VEHICLE,
    WEIGHT_RIDER,
    WEIGHT_ATTRIBUTES,
    WEIGHT_SPACE_TIME,
    score_candidates,
)


def load_crop(name):
    path = CROPS / name
    img = cv2.imread(str(path))
    if img is None:
        print(f"  !! could not read crop: {name}")
    return img


def build_fingerprints(names):
    """name -> fingerprint dict, via the REAL production fingerprint()."""
    out = {}
    for name in names:
        img = load_crop(name)
        if img is None:
            continue
        out[name] = fingerprint(img)  # rider_crop=None, passenger_count=None (honest: not available here)
    return out


def main():
    data = json.loads((LABELSET / "labels.json").read_text(encoding="utf-8"))
    pairs, incidents = data["pairs"], data["incidents"]

    wanted = {p["a"] for p in pairs} | {p["b"] for p in pairs}
    for entry in incidents.values():
        wanted.add(entry["origin"])
        wanted.update(c["crop"] for c in entry["candidates"])

    print(f"\n  Building real fingerprints for {len(wanted)} crops via pipeline.fingerprint.fingerprint() ...")
    fps = build_fingerprints(sorted(wanted))

    print(f"\n  CURRENT PRODUCTION WEIGHTS (pipeline/matcher.py)")
    print(f"    vehicle={WEIGHT_VEHICLE}  rider={WEIGHT_RIDER}  "
          f"attributes={WEIGHT_ATTRIBUTES}  space_time={WEIGHT_SPACE_TIME}")

    # ---- cross-camera pair margin, using the REAL fused score ----
    def fused_score(name_a, name_b, dist_m=None, time_s=None):
        fp_a, fp_b = fps.get(name_a), fps.get(name_b)
        if fp_a is None or fp_b is None:
            return None
        incident = {"sighting_id": "a", "veh_emb": fp_a["veh_emb"], "rider_emb": fp_a["rider_emb"], "attrs": fp_a["attrs"]}
        candidate = {
            "sighting_id": "b", "veh_emb": fp_b["veh_emb"], "rider_emb": fp_b["rider_emb"], "attrs": fp_b["attrs"],
            "distance_m": dist_m, "time_gap_seconds": time_s,
        }
        result = score_candidates(incident, [candidate])[0]
        return result["score"], result["breakdown"]

    rows = []
    for pair in pairs:
        if pair["kind"] != "cross_camera":
            continue
        r = fused_score(pair["a"], pair["b"], pair.get("distance_m"), pair.get("time_gap_seconds"))
        if r is None:
            continue
        score, breakdown = r
        rows.append((score, pair["same_vehicle"], breakdown))

    same = [s for s, is_same, _ in rows if is_same]
    diff = [s for s, is_same, _ in rows if not is_same]

    print("\n  REAL PRODUCTION FUSED MATCHER (fingerprint() + score_candidates(), current weights)")
    if same:
        print(f"    same vehicle       n={len(same):<3} {min(same):.3f} - {max(same):.3f}")
    else:
        print("    same vehicle       none")
    if diff:
        print(f"    different vehicle  n={len(diff):<3} {min(diff):.3f} - {max(diff):.3f}")
    if same and diff:
        margin = min(same) - max(diff)
        verdict = "SEPARATES" if margin > 0 else "OVERLAPS - no threshold works"
        print(f"    margin             {margin:+.3f}   {verdict}")

    # ---- rank-1 on incidents, using the REAL fused score ----
    hits, total = 0, 0
    print("\n  RANK-1 (real fused matcher)")
    for incident_id, entry in incidents.items():
        origin_fp = fps.get(entry["origin"])
        truth = [c["crop"] for c in entry["candidates"] if c["same_vehicle"]]
        if origin_fp is None or not truth:
            continue
        total += 1
        scored = []
        for c in entry["candidates"]:
            r = fused_score(entry["origin"], c["crop"], c.get("distance_m"), c.get("time_gap_seconds"))
            if r is None:
                continue
            scored.append((r[0], c["same_vehicle"], c["crop"]))
        scored.sort(key=lambda x: x[0], reverse=True)
        position = next((i for i, (_, is_same, _) in enumerate(scored, 1) if is_same), None)
        if position:
            hits += position == 1
            print(f"    {incident_id[:8]}  true match at position {position} of {len(scored)}  "
                  f"{'OK' if position == 1 else 'MISS'}")
    if total:
        print(f"    rank-1  {hits}/{total}")
    else:
        print("    no incident has a confirmed match yet")

    # ---- honesty report: which signals were actually live ----
    any_rider = any(fp["rider_emb"] is not None for fp in fps.values())
    any_spacetime = any(
        (p.get("distance_m") is not None and p.get("time_gap_seconds") is not None) for p in pairs
    )
    print("\n  SIGNALS ACTUALLY EXERCISED IN THIS RUN")
    print(f"    vehicle (veh_emb)      YES — real production embedding")
    print(f"    rider (rider_emb)      {'YES' if any_rider else 'NO — crops are single union images, no separate rider crop available'}")
    print(f"    attributes (colour)    YES — real production colour histogram")
    print(f"    space_time             {'YES' if any_spacetime else 'NO — labels.json has no distance_m/time_gap_seconds'}")
    if not any_rider or not any_spacetime:
        print(f"\n    Missing signals had their weight redistributed to the ones above by")
        print(f"    score_candidates()'s own logic — this is what production would ALSO do")
        print(f"    if rider_emb or space-time data were missing on a real sighting. So this")
        print(f"    number is honest about a real code path, not an isolated best-case test —")
        print(f"    but it is still not the FULL signal set the system is designed to use.")

    print()


if __name__ == "__main__":
    main()
