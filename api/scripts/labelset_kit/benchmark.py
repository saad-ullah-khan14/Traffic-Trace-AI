r"""Is this fingerprint model better than the one we ship? Answer in one command.

    python benchmark.py

Standalone: needs numpy, pillow, torch and whatever your model needs. No
database, no API, no project imports. Everything it measures comes from
labels.json, which holds the officer's own decisions on real street footage.

  ------------------------------------------------------------------
  THE ONLY THING YOU EDIT IS embed().  Everything below it is scoring.
  ------------------------------------------------------------------

The three numbers that decide whether a change is kept:

  margin    worst same-vehicle pair minus best different-vehicle pair, on
            CROSS-CAMERA pairs. Positive means one threshold separates them.
            Negative means no threshold can, however it is tuned.

  rank-1    of the incidents that have a confirmed match, how many put that
            match first. This is what the officer actually experiences.

  ms/crop   speed on this CPU. The live machine manages ~1.2 frames/s and the
            queue is a latency budget, not a buffer. A model that is twice as
            slow can be worse in practice even if it scores better.

Burst pairs (two frames of one pass at one camera) are reported separately as a
floor, never mixed into the headline. They are an easier problem — a model that
cannot separate those cannot separate anything.

Two baselines print every run, and they are NOT the same thing:

    shipped fused score       margin  -0.066   rank-1  1/2
      what the officer actually sees: CLIP vehicle + CLIP rider + colour
      histogram, fused by pipeline/matcher.py. Read from labels.json.

    this script's embedder    margin  +0.018   rank-1  2/2
      raw cosine on the saved evidence crop, which includes the rider.

The second beats the first on the same 12 pairs. That gap is a lead, not a
conclusion — there are only 2 confirmed cross-camera pairs so far, and a margin
built on 2 positives is fragile. Collect more labels before acting on it. What
it points at: the colour histogram carries the largest effective weight (0.46)
and the worst separation (-0.364), and the union crop may be a better input than
the tight vehicle box the pipeline embeds today.
"""

import json
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
CROPS = HERE / "crops"


# ===========================================================================
#  EDIT THIS FUNCTION ONLY
# ===========================================================================

def build_embedder():
    """Return a function crop_path -> 1-D numpy vector.

    Load the model ONCE here, not per crop.

    The shipped baseline is below. To test a different model, replace the body
    and leave everything else alone. Three rules:

      1. Return an L2-normalized vector (the API verifies this and warns).
      2. Note the dimension it returns. If it is not 512, that is a schema
         change on the backend side — say so in your report, do not pad or
         truncate to fit.
      3. Cache the weights locally. The demo machine has no internet.

    DINOv2 via timm, for reference (timm is already in the API venv):

        import timm, torch
        from PIL import Image
        model = timm.create_model("vit_small_patch14_dinov2.lvd142m",
                                  pretrained=True, num_classes=0).eval()
        cfg = timm.data.resolve_data_config({}, model=model)
        tf = timm.data.create_transform(**cfg)
        def embed(path):
            with torch.no_grad():
                v = model(tf(Image.open(path).convert("RGB")).unsqueeze(0))[0]
            v = v.numpy().astype(np.float32)
            return v / np.linalg.norm(v)
        return embed, "DINOv2 ViT-S/14 (384-d)"
    """
    import open_clip
    import torch
    from PIL import Image

    model, _, preprocess = open_clip.create_model_and_transforms(
        "ViT-B-32-quickgelu", pretrained="openai"
    )
    model.eval()

    def embed(path):
        image = preprocess(Image.open(path).convert("RGB")).unsqueeze(0)
        with torch.no_grad():
            vector = model.encode_image(image)[0].numpy().astype(np.float32)
        return vector / np.linalg.norm(vector)

    return embed, "CLIP ViT-B-32 (512-d, shipped baseline)"


# ===========================================================================
#  Scoring — no need to change anything below
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
    print(f"  speed      {1000 * elapsed / max(1, len(vectors)):.1f} ms/crop  "
          f"({len(vectors)} crops)")

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
        label = "CROSS-CAMERA  (the real task)" if headline else "BURST  (floor, easier)"
        print(f"\n  {label}")
        print(f"    same vehicle       n={len(same):<3} {min(same):.3f} - {max(same):.3f}"
              if same else "    same vehicle       none")
        if diff:
            print(f"    different vehicle  n={len(diff):<3} {min(diff):.3f} - {max(diff):.3f}")
            margin = min(same) - max(diff)
            verdict = "SEPARATES" if margin > 0 else "overlaps - no threshold works"
            print(f"    margin             {margin:+.3f}   {verdict}")
        else:
            print("    different vehicle  none (nothing to separate against)")

    # The shipped fused score, straight from labels.json — the number the officer
    # actually saw. Printed every run so a new model is compared against what is
    # live, not against this script's own default embedder.
    fused = [(p["baseline_score"], p["same_vehicle"]) for p in pairs
             if p["kind"] == "cross_camera" and p["baseline_score"] is not None]
    fused_same = [s for s, is_same in fused if is_same]
    fused_diff = [s for s, is_same in fused if not is_same]
    if fused_same and fused_diff:
        print("\n  SHIPPED FUSED SCORE  (reference — vehicle + rider + colour)")
        print(f"    same vehicle       n={len(fused_same):<3} "
              f"{min(fused_same):.3f} - {max(fused_same):.3f}")
        print(f"    different vehicle  n={len(fused_diff):<3} "
              f"{min(fused_diff):.3f} - {max(fused_diff):.3f}")
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
        print(f"    {incident[:8]}  true match at position {position} of {len(ranked)}"
              f"  {'OK' if position == 1 else 'MISS'}")
    if total:
        print(f"    rank-1  {hits}/{total}")
    else:
        print("    no incident has a confirmed match yet")

    print("\n  Keep the change only if margin improves AND rank-1 does not drop.\n")


if __name__ == "__main__":
    main()
