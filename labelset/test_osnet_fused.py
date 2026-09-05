"""
OSNet embedding + our REAL production fused matcher (color histogram +
weights), tested on the 24-pair labelset. This answers: if we swap CLIP for
OSNet as the embedder, what does the FULL fused score (not just raw cosine)
look like?
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # project root (Traffic_Trace/)

import cv2
import numpy as np
from torchreid.reid.utils import FeatureExtractor

from pipeline.fingerprint import _color_histogram
from pipeline.matcher import score_candidates

HERE = Path(__file__).resolve().parent
CROPS = HERE / "crops"

extractor = FeatureExtractor(model_name="osnet_x1_0", device="cpu")


def osnet_embed(path):
    features = extractor(str(path))
    vector = features[0].numpy().astype(np.float32)
    return vector / np.linalg.norm(vector)


data = json.loads((HERE / "labels.json").read_text(encoding="utf-8"))
pairs, incidents = data["pairs"], data["incidents"]

wanted = {p["a"] for p in pairs} | {p["b"] for p in pairs}
for entry in incidents.values():
    wanted.add(entry["origin"])
    wanted.update(c["crop"] for c in entry["candidates"])

fps = {}
for crop_name in sorted(wanted):
    path = CROPS / crop_name
    if not path.exists():
        continue
    img = cv2.imread(str(path))
    if img is None:
        continue
    veh_emb = osnet_embed(path)
    hist = _color_histogram(img)
    fps[crop_name] = {
        "veh_emb": veh_emb.tolist(),
        "rider_emb": None,
        "attrs": {"color_histogram": hist, "passenger_count": None},
    }

print(f"Fingerprinted {len(fps)} crops with OSNet + our color histogram\n")


def make_sighting(sid, fp):
    return {
        "sighting_id": sid,
        "veh_emb": fp["veh_emb"],
        "rider_emb": fp["rider_emb"],
        "attrs": fp["attrs"],
    }


cross_pairs = [p for p in pairs if p["kind"] == "cross_camera" and p["a"] in fps and p["b"] in fps]
same_scores, diff_scores = [], []
for pair in cross_pairs:
    incident = make_sighting("a", fps[pair["a"]])
    candidate = make_sighting("b", fps[pair["b"]])
    result = score_candidates(incident, [candidate])[0]
    (same_scores if pair["same_vehicle"] else diff_scores).append(result["score"])

print("=== OSNet + OUR FUSED MATCHER (color hist + weights) on 24-pair labelset ===")
print(f"  same vehicle       n={len(same_scores)}  {min(same_scores):.3f} - {max(same_scores):.3f}")
print(f"  different vehicle  n={len(diff_scores)}  {min(diff_scores):.3f} - {max(diff_scores):.3f}")
margin = min(same_scores) - max(diff_scores)
print(f"  margin             {margin:+.3f}   {'SEPARATES' if margin > 0 else 'overlaps - no threshold works'}")

print("\n=== RANK-1 with OSNet + our fused matcher ===")
hits, total = 0, 0
for incident_id, entry in incidents.items():
    if entry["origin"] not in fps:
        continue
    truth = [c["crop"] for c in entry["candidates"] if c["same_vehicle"]]
    if not truth:
        continue
    total += 1

    origin_sighting = make_sighting("origin", fps[entry["origin"]])
    candidate_sightings = [
        make_sighting(c["crop"], fps[c["crop"]])
        for c in entry["candidates"] if c["crop"] in fps
    ]
    scored = score_candidates(origin_sighting, candidate_sightings)
    ranked = sorted(scored, key=lambda r: r["score"], reverse=True)

    crop_to_label = {c["crop"]: c["same_vehicle"] for c in entry["candidates"]}
    position = next(i for i, r in enumerate(ranked, 1) if crop_to_label.get(r["sighting_id"]))
    hits += position == 1
    print(f"  {incident_id[:8]}  true match at position {position} of {len(ranked)}  "
          f"{'OK' if position == 1 else 'MISS'}")

if total:
    print(f"  rank-1  {hits}/{total}")

print("\nCompare against: shipped fused (CLIP) margin -0.077, rank-1 3/3")
