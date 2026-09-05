"""
Phase 4 — Helmet module.

check_helmet(frame, rider_bbox) -> "helmet" | "no_helmet" | "unknown"

IMPORTANT DESIGN NOTE: we run the model on the FULL frame, not a tight crop
of the rider. The model was trained on full traffic-scene images where a
helmet is a small object within a big photo. A tight crop changes the
object's apparent scale and confuses the model — tested and confirmed on
our own data. Running on the full frame matches the training distribution,
then we just match the resulting helmet detections to the right rider by
bbox overlap (same trick as motorcycle/rider association in detector.py).
"""

import os
from ultralytics import YOLO
import logging

_logger = logging.getLogger(__name__)

MODEL_PATH = os.path.join(os.path.dirname(__file__), "helmet_model.pt")
_model = YOLO(MODEL_PATH)

HELMET_CLASSES = {0}       # helmet
NO_HELMET_CLASSES = {1}    # no_helmet

CONFIDENCE_THRESHOLD = 0.10


def _box_overlaps_rider(detection_box, rider_bbox, min_overlap_fraction=0.3):
    """
    True if the helmet-model's detection box substantially covers the
    rider's bbox. The helmet model outputs near-full-body boxes (head to
    torso), not tight head-only boxes — so matching by "is the box's
    center near the top of the rider" fails whenever the detection box is
    large. Matching by overlap fraction (how much of the RIDER is covered)
    works regardless of the detection box's own size or shape.
    """
    dx1, dy1, dx2, dy2 = detection_box
    rx1, ry1, rx2, ry2 = rider_bbox

    ix1, iy1 = max(dx1, rx1), max(dy1, ry1)
    ix2, iy2 = min(dx2, rx2), min(dy2, ry2)
    inter_w, inter_h = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter_area = inter_w * inter_h

    rider_area = max(1, (rx2 - rx1) * (ry2 - ry1))
    return (inter_area / rider_area) > min_overlap_fraction


def check_helmet(frame, rider_bbox):
    """
    ...
    """
    results = _model.predict(source=frame, conf=CONFIDENCE_THRESHOLD, verbose=False)
    result = results[0]

    if result.boxes is None or len(result.boxes) == 0:
        _logger.info(f"[check_helmet] status='unknown' confidence=0.000 rider_bbox={rider_bbox} (no boxes at all)")
        return {"status": "unknown", "confidence": 0.0}

    best_label = "unknown"
    best_conf = 0.0

    for box in result.boxes:
        box_xyxy = box.xyxy[0].tolist()
        if not _box_overlaps_rider(box_xyxy, rider_bbox):
            continue

        conf = float(box.conf[0])
        if conf <= best_conf:
            continue

        cls_id = int(box.cls[0])
        if cls_id in HELMET_CLASSES:
            best_label, best_conf = "helmet", conf
        elif cls_id in NO_HELMET_CLASSES:
            best_label, best_conf = "no_helmet", conf

    _logger.info(
        f"[check_helmet] status={best_label!r} confidence={best_conf:.3f} "
        f"rider_bbox={rider_bbox}"
    )

    return {"status": best_label, "confidence": round(best_conf, 4)}

if __name__ == "__main__":
    print("Model classes:", _model.names)