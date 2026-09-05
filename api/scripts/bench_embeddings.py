r"""Does the score fusion identify a vehicle better than the CLIP embedding alone?

The whole product rests on recognising the same vehicle at a second camera. Phase 7
measured that CLIP cosine alone gets this wrong — a *different*-vehicle pair outscored
a *same*-vehicle pair. score_candidates is supposed to fix that by weighting CLIP
lowest (0.20) and leaning on the colour histogram and space-time instead.

This script tests that claim on the paired test images: a1/a2 are one motorcycle,
b1/b2 are a different one. It reports, for every pair, the raw veh_emb cosine and the
full fused score, then the separation margin of each:

    margin = worst same-vehicle pair - best different-vehicle pair

Positive means the signal ranks every same-vehicle pair above every different-vehicle
pair, so one threshold separates them. Negative means it does not.

    cd api
    .\.venv\Scripts\python.exe -m scripts.bench_embeddings
    .\.venv\Scripts\python.exe -m scripts.bench_embeddings --distance-m 1373 --time-gap 180
"""

import argparse
import itertools
import sys
from pathlib import Path

import numpy as np

from app.services.pipeline_client import PIPELINE_AVAILABLE, PIPELINE_STATUS, process_frame, score_candidates

DEFAULT_DIR = Path(r"D:\Downloads\project (3)\project\test_images")
# a1/a2 = one motorcycle, b1/b2 = a different one.
IMAGES = {"a1": "a1.png", "a2": "a2.png", "b1": "b1.png", "b2": "b2.png"}


def pick_detection(detections):
    """The subject vehicle: prefer a motorcycle, else the most confident detection."""
    if not detections:
        return None
    bikes = [d for d in detections if d["vehicle_type"] == "motorcycle"]
    pool = bikes or detections
    return max(pool, key=lambda d: d.get("confidence") or 0.0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    parser.add_argument("--distance-m", type=float, default=1373.0,
                        help="camera separation used for the space-time signal")
    parser.add_argument("--time-gap", type=float, default=180.0,
                        help="seconds between the two sightings")
    args = parser.parse_args()

    print(f"pipeline: {PIPELINE_STATUS}")
    if not PIPELINE_AVAILABLE:
        print("ERROR: the stub generates random embeddings — this measures nothing.")
        return 1

    subjects = {}
    for key, filename in IMAGES.items():
        path = args.dir / filename
        if not path.exists():
            print(f"ERROR: {path} not found")
            return 1
        detections = process_frame(path.read_bytes(), "bench", "2026-08-24T00:00:00Z")
        chosen = pick_detection(detections)
        if chosen is None:
            print(f"ERROR: no detections in {filename}")
            return 1
        subjects[key] = chosen
        hist = (chosen.get("attrs") or {}).get("color_histogram")
        print(f"  {key}: {len(detections)} detections, using {chosen['vehicle_type']} "
              f"conf={chosen.get('confidence')} rider_emb={'yes' if chosen.get('rider_emb') else 'no'} "
              f"hist={'yes' if hist else 'no'}")

    # Same vehicle photographed twice vs two different vehicles.
    labels = {("a1", "a2"): "same", ("b1", "b2"): "same"}
    rows = []
    for left, right in itertools.combinations(IMAGES, 2):
        kind = labels.get((left, right), "diff")
        incident = subjects[left]
        candidate = {**subjects[right], "sighting_id": right,
                     "distance_m": args.distance_m, "time_gap_seconds": args.time_gap}

        cosine = float(np.dot(np.array(incident["veh_emb"]), np.array(candidate["veh_emb"])))
        fused = score_candidates(incident, [candidate])[0]
        rows.append((f"{left} <-> {right}", kind, cosine, fused["score"], fused["breakdown"]))

    print(f"\n  distance_m={args.distance_m:.0f}  time_gap_seconds={args.time_gap:.0f}\n")
    header = f"  {'pair':<14}{'kind':<7}{'raw cosine':>11}{'fused':>8}   breakdown"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for pair, kind, cosine, fused, breakdown in rows:
        parts = " ".join(f"{k[:4]}={v:.3f}" for k, v in breakdown.items())
        print(f"  {pair:<14}{kind:<7}{cosine:>11.4f}{fused:>8.4f}   {parts}")

    def margin(index):
        same = [r[index] for r in rows if r[1] == "same"]
        diff = [r[index] for r in rows if r[1] == "diff"]
        return min(same) - max(diff), min(same), max(diff)

    raw_margin, raw_same, raw_diff = margin(2)
    fused_margin, fused_same, fused_diff = margin(3)

    print(f"\n  raw veh_emb cosine : worst same {raw_same:.4f}  best diff {raw_diff:.4f}"
          f"  margin {raw_margin:+.4f}  {'SEPARATES' if raw_margin > 0 else 'DOES NOT SEPARATE'}")
    print(f"  fused score        : worst same {fused_same:.4f}  best diff {fused_diff:.4f}"
          f"  margin {fused_margin:+.4f}  {'SEPARATES' if fused_margin > 0 else 'DOES NOT SEPARATE'}")
    print(f"\n  fusion {'BEATS' if fused_margin > raw_margin else 'DOES NOT BEAT'} the raw embedding "
          f"({fused_margin:+.4f} vs {raw_margin:+.4f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
