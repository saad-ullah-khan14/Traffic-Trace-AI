r"""Retest OSNet (person re-ID) on the FULL 24-pair labelset.

PROBLEMS.txt Problem 2 says this explicitly:
    "OSNet (person re-ID)  margin -0.048, 512-d, 103 ms/crop"
    "IMPORTANT: all three were tested on only 2 confirmed pairs. There are
    now 24. Those tests are worth repeating, and person re-ID (OSNet) is
    still the most promising — on commuter motorcycles the RIDER is the
    distinctive part, and a person re-ID model is trained on exactly the
    question we are asking."

This is a drop-in replacement for labelset/benchmark.py's build_embedder() —
same file, same scoring, only the embedder changed. Copy this into
labelset/ (next to labels.json and crops/) and run it there:

    cd labelset
    python osnet_retest.py

Needs: pip install torchreid --break-system-packages
       (or: pip install git+https://github.com/KaiyangZhou/deep-person-reid.git)
If torchreid is painful to install on this machine, say so and we fall back
to timm's OSNet weights instead — do not spend more than 15 minutes on
install friction before falling back.
"""

import json
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
CROPS = HERE / "crops"


def build_embedder():
    """OSNet re-ID embedder — person-identity model, not scene/category like CLIP."""
    import torch
    from PIL import Image
    from torchvision import transforms

    try:
        import torchreid
    except ImportError as e:
        raise SystemExit(
            "torchreid not installed. Run:\n"
            "  pip install torchreid --break-system-packages\n"
            "If that fails on this machine, tell Claude — do not burn time on it."
        ) from e

    model = torchreid.models.build_model(
        name="osnet_x1_0", num_classes=1000, pretrained=True
    )
    model.eval()

    tf = transforms.Compose([
        transforms.Resize((256, 128)),  # OSNet's standard person re-ID input size
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])

    def embed(path):
        img = Image.open(path).convert("RGB")
        tensor = tf(img).unsqueeze(0)
        with torch.no_grad():
            vector = model(tensor)[0].numpy().astype(np.float32)
        return vector / np.linalg.norm(vector)

    return embed, "OSNet x1.0 (512-d, person re-ID) — retest on 24 pairs"


# ===========================================================================
#  Scoring — identical to labelset/benchmark.py, unchanged on purpose so the
#  numbers are directly comparable to the shipped baseline printed alongside.
# ===========================================================================

def cosine(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def main():
    data = json.loads((HERE / "labels.json").read_text(encoding="utf-8"))
    pairs, incidents = data["pairs"], data["incidents"]

    embed, name = build_embedder()

    wanted = {p["a"] for p in pairs} | {p["b"] for p in pairs}
    for entry in incidents.values():
        wanted.add(entry["origin"])
        wanted.update(c["crop"] for c in entry["candidates"])

    vectors, elapsed = {}, 0.0
    for crop in sorted(wanted):
        path = CROPS / crop
        if not path.exists():
            continue
        start = time.perf_counter()
        vectors[crop] = embed(path)
        elapsed += time.perf_counter() - start

    dim = len(next(iter(vectors.values())))
    print(f"\n  model      {name}")
    print(f"  dimension  {dim}" + ("" if dim == 512 else "   <-- NOT 512: schema change on the backend"))
    print(f"  speed      {1000 * elapsed / max(1, len(vectors)):.1f} ms/crop  ({len(vectors)} crops)")

    def scored(kind):
        out = []
        for pair in pairs:
            if pair["kind"] != kind:
                continue
            if pair["a"] not in vectors or pair["b"] not in vectors:
                continue
            out.append((cosine(vectors[pair["a"]], vectors[pair["b"]]), pair["same_vehicle"]))
        return out

    for kind, headline in (("cross_camera", True), ("burst", False)):
        rows = scored(kind)
        if not rows:
            continue
        same = [s for s, is_same in rows if is_same]
        diff = [s for s, is_same in rows if not is_same]
        label = "CROSS-CAMERA  (the real task, n=24 now, not 2)" if headline else "BURST  (floor, easier)"
        print(f"\n  {label}")
        print(f"    same vehicle       n={len(same):<3} {min(same):.3f} - {max(same):.3f}" if same else "    same vehicle       none")
        if diff:
            print(f"    different vehicle  n={len(diff):<3} {min(diff):.3f} - {max(diff):.3f}")
            margin = min(same) - max(diff)
            verdict = "SEPARATES" if margin > 0 else "overlaps - no threshold works"
            print(f"    margin             {margin:+.3f}   {verdict}")

    fused = [(p["baseline_score"], p["same_vehicle"]) for p in pairs
             if p["kind"] == "cross_camera" and p["baseline_score"] is not None]
    fused_same = [s for s, is_same in fused if is_same]
    fused_diff = [s for s, is_same in fused if not is_same]
    if fused_same and fused_diff:
        print("\n  SHIPPED FUSED SCORE  (reference — current production, from labels.json)")
        print(f"    same vehicle       n={len(fused_same):<3} {min(fused_same):.3f} - {max(fused_same):.3f}")
        print(f"    different vehicle  n={len(fused_diff):<3} {min(fused_diff):.3f} - {max(fused_diff):.3f}")
        print(f"    margin             {min(fused_same) - max(fused_diff):+.3f}")

    hits, total = 0, 0
    print("\n  RANK-1  (does the confirmed match come first?)")
    for incident, entry in incidents.items():
        truth = [c["crop"] for c in entry["candidates"] if c["same_vehicle"]]
        if not truth or entry["origin"] not in vectors:
            continue
        total += 1
        ranked = sorted(
            (c for c in entry["candidates"] if c["crop"] in vectors),
            key=lambda c: cosine(vectors[entry["origin"]], vectors[c["crop"]]),
            reverse=True,
        )
        position = next(i for i, c in enumerate(ranked, 1) if c["same_vehicle"])
        hits += position == 1
        print(f"    {incident[:8]}  true match at position {position} of {len(ranked)}  {'OK' if position == 1 else 'MISS'}")
    if total:
        print(f"    rank-1  {hits}/{total}")

    print("\n  Keep OSNet only if margin improves over -0.077/-0.131 (current) AND rank-1 stays 3/3.\n")
    print("  Remember (PART 3, PROBLEMS.txt): OSNet was rejected once on 2 pairs.")
    print("  This run uses 24. Trust THIS number over the old one — more data wins.\n")


if __name__ == "__main__":
    main()
