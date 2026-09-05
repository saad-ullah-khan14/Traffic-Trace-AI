"""
Phase 5 — Fingerprint module.

fingerprint(vehicle_crop, rider_crop=None) -> dict
    Turns a vehicle (and optionally its rider) crop into a "fingerprint":
    a normalized embedding vector + basic visual attributes (color, etc).
    Used later to match the same vehicle seen at different cameras.

NOTE on accuracy: CLIP's embedding alone is a fairly weak identity signal
(it captures general scene semantics more than fine-grained vehicle
identity — tested and confirmed on our own data). We compensate by also
returning a color histogram in attrs, which Phase 9's score fusion uses
as a second, independent signal. Matching should never rely on veh_emb
alone.
"""

import cv2
import numpy as np
import open_clip
import torch

# Load CLIP once at import time.
_device = "cuda" if torch.cuda.is_available() else "cpu"
_model, _, _preprocess = open_clip.create_model_and_transforms(
    "ViT-B-32-quickgelu", pretrained="openai"
)
_model.to(_device)
_model.eval()

EMBEDDING_DIM = 512  # must match pipeline/types.py and the agreed contract with Muhammad


def _embed(crop_bgr):
    """
    crop_bgr: numpy BGR image (OpenCV format).
    Returns: normalized (L2 norm = 1.0) numpy array of length 512.
    """
    from PIL import Image

    crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(crop_rgb)
    tensor = _preprocess(pil_img).unsqueeze(0).to(_device)

    with torch.no_grad():
        emb = _model.encode_image(tensor)
        emb = emb.cpu().numpy().flatten().astype(np.float32)

    # L2-normalize — REQUIRED per the contract with Muhammad's backend.
    norm = np.linalg.norm(emb)
    if norm > 0:
        emb = emb / norm

    return emb


def _dominant_color(crop_bgr):
    """
    Human-readable color name — used for the `attrs["color"]` display field.
    """
    if crop_bgr is None or crop_bgr.size == 0:
        return "unknown"

    hsv = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2HSV)
    h = np.median(hsv[:, :, 0])
    s = np.median(hsv[:, :, 1])
    v = np.median(hsv[:, :, 2])

    if v < 50:
        return "black"
    if s < 40:
        return "white" if v > 180 else "gray"

    if h < 10 or h >= 170:
        return "red"
    elif h < 25:
        return "orange"
    elif h < 35:
        return "yellow"
    elif h < 85:
        return "green"
    elif h < 130:
        return "blue"
    elif h < 170:
        return "purple"
    return "unknown"


def _color_histogram(crop_bgr, bins=8):
    """
    Returns a normalized HSV hue histogram (`bins` buckets) as a list of
    floats summing to 1.0. This is a much stronger identity signal than a
    single color name — two vehicles with different paint will have very
    different histograms even when CLIP's semantic embedding confuses them.
    Used by Phase 9's score fusion as the "attribute overlap" signal.
    """
    if crop_bgr is None or crop_bgr.size == 0:
        return [0.0] * bins

    hsv = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0], None, [bins], [0, 180])
    hist = hist.flatten()
    total = hist.sum()
    if total > 0:
        hist = hist / total
    return hist.tolist()


def fingerprint(vehicle_crop, rider_crop=None, passenger_count=None, helmet_color=None):
    """
    vehicle_crop: numpy BGR image, cropped to the vehicle's bbox.
    rider_crop: numpy BGR image, cropped to the rider's bbox, or None.
    passenger_count: int, how many riders are on this vehicle (from detect()'s
        rider_count). Optional — omitted from attrs if not given.
    helmet_color: str, dominant color of the rider's helmet region, if known
        (computed by the caller — e.g. orchestrator.py — from the top portion
        of the rider crop). Optional — omitted from attrs if not given.

    Returns: dict matching pipeline/types.py's Fingerprint shape:
        {
            "veh_emb": list[float],          # length 512, L2-normalized
            "rider_emb": list[float] | None, # length 512, or None
            "attrs": {
                "color": str,
                "color_histogram": list[float],  # length 8, sums to 1.0
                "passenger_count": int | None,
                "helmet_color": str | None,
            }
        }
    """
    veh_emb = _embed(vehicle_crop)
    rider_emb = _embed(rider_crop) if rider_crop is not None and rider_crop.size > 0 else None

    attrs = {
        "color": _dominant_color(vehicle_crop),
        "color_histogram": _color_histogram(vehicle_crop),
        "passenger_count": passenger_count,
        "helmet_color": helmet_color,
    }

    return {
        "veh_emb": veh_emb.tolist(),
        "rider_emb": rider_emb.tolist() if rider_emb is not None else None,
        "attrs": attrs,
    }
def _embed_batch(crops):
    """
    crops: list of numpy BGR images (some entries may be None or empty).
    Returns: list of normalized (L2=1) numpy arrays, length 512 each, same
    order/length as input. None/empty crops get None back at that position.

    This is the speed fix for Phase 15 — running N separate CLIP calls is
    far slower than one batched forward pass over N images. Measured on our
    own data: fingerprinting was ~85% of total process_frame time when done
    one-crop-at-a-time.
    """
    from PIL import Image

    valid_indices = []
    tensors = []
    for i, crop in enumerate(crops):
        if crop is None or crop.size == 0:
            continue
        crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(crop_rgb)
        tensors.append(_preprocess(pil_img))
        valid_indices.append(i)

    results = [None] * len(crops)
    if not tensors:
        return results

    batch = torch.stack(tensors).to(_device)
    with torch.no_grad():
        embs = _model.encode_image(batch)
        embs = embs.cpu().numpy().astype(np.float32)

    for idx, emb in zip(valid_indices, embs):
        norm = np.linalg.norm(emb)
        if norm > 0:
            emb = emb / norm
        results[idx] = emb

    return results


def fingerprint_batch(vehicle_crops, rider_crops=None, passenger_counts=None, helmet_colors=None):
    """
    Batched version of fingerprint() — processes ALL vehicles in a frame
    with a single CLIP forward pass instead of one call per vehicle.

    vehicle_crops: list[np.ndarray]
    rider_crops: list[np.ndarray | None], same length as vehicle_crops (optional)
    passenger_counts: list[int | None], same length (optional)
    helmet_colors: list[str | None], same length (optional)

    Returns: list[dict], same shape as individual fingerprint() calls,
    in the same order as the input lists.
    """
    n = len(vehicle_crops)
    rider_crops = rider_crops if rider_crops is not None else [None] * n
    passenger_counts = passenger_counts if passenger_counts is not None else [None] * n
    helmet_colors = helmet_colors if helmet_colors is not None else [None] * n

    veh_embs = _embed_batch(vehicle_crops)
    rider_embs = _embed_batch(rider_crops)

    results = []
    for i in range(n):
        veh_emb = veh_embs[i]
        if veh_emb is None:
            # A vehicle crop should never be empty in practice (orchestrator
            # skips zero-area crops before this point), but fall back safely.
            veh_emb = np.zeros(EMBEDDING_DIM, dtype=np.float32)
        rider_emb = rider_embs[i]

        attrs = {
            "color": _dominant_color(vehicle_crops[i]),
            "color_histogram": _color_histogram(vehicle_crops[i]),
            "passenger_count": passenger_counts[i],
            "helmet_color": helmet_colors[i],
        }

        results.append(
            {
                "veh_emb": veh_emb.tolist(),
                "rider_emb": rider_emb.tolist() if rider_emb is not None else None,
                "attrs": attrs,
            }
        )

    return results


if __name__ == "__main__":
    # Quick manual check: python -m pipeline.fingerprint <image_path>
    import sys
    from pipeline.detector import detect

    path = sys.argv[1] if len(sys.argv) > 1 else "test_images/street1.jpg"
    frame = cv2.imread(path)
    detections = detect(path)

    for d in detections:
        x1, y1, x2, y2 = [int(v) for v in d["bbox"]]
        crop = frame[y1:y2, x1:x2]
        fp = fingerprint(crop)
        print(f"{d['vehicle_type']}: color={fp['attrs']['color']}, emb_len={len(fp['veh_emb'])}")