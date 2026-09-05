"""
Phase 3 — Detection module.

detect(img) -> list of dicts, one per vehicle, each with its attached rider
(if any). Persons are NOT returned standalone — only as riders attached to
a vehicle, since that's what the pipeline actually needs downstream.
"""

import os

from ultralytics import YOLO

# Load once at import time — loading per-call would be way too slow.
# Path is relative to this file, not the working directory: the API runs from
# api/, where a bare "yolov8n.pt" does not exist. Same pattern as helmet.py.
_model = YOLO(os.path.join(os.path.dirname(__file__), "yolov8n.pt"))

# PRODUCT DECISION (30 Aug 2026, Daniyal): motorcycles only, for now.
#
# The only violation this system detects is no_helmet, which no car, bus or
# truck can ever commit. Every other class was therefore pure cost with no
# possible payoff, and worse than free: measured on real street footage,
# 40 of 53 sightings were cars, and they took 16 of the 20 candidate slots
# offered to the officer for a motorcycle incident. The bike that mattered was
# competing with parked traffic for a place on the review screen.
#
# Detection still finds them — YOLO classifies everything — they are simply not
# returned, so they are never fingerprinted, stored, ranked or watched. That
# also cuts the fingerprinting cost, which is ~71% of frame time.
#
# Add a class back here the day a violation exists that applies to it.
VEHICLE_CLASSES = {"motorcycle"}
PERSON_CLASS = "person"

CONFIDENCE_THRESHOLD = 0.4


def _boxes_overlap_or_above(person_box, vehicle_box):
    """
    True if the person box meaningfully overlaps the vehicle box, or sits
    just above it (typical for a rider's head poking above a motorcycle's
    bounding box — the motorcycle box usually only covers wheels/frame/seat,
    not the rider standing/sitting on it).
    """
    px1, py1, px2, py2 = person_box
    vx1, vy1, vx2, vy2 = vehicle_box

    ix1, iy1 = max(px1, vx1), max(py1, vy1)
    ix2, iy2 = min(px2, vx2), min(py2, vy2)
    inter_w, inter_h = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter_area = inter_w * inter_h
    person_area = max(1, (px2 - px1) * (py2 - py1))

    if inter_area / person_area > 0.3:
        return True

    horizontal_overlap = px1 < vx2 and px2 > vx1
    margin = (vy2 - vy1) * 0.3
    if horizontal_overlap and py2 <= vy1 and (vy1 - py2) < margin:
        return True

    return False


def detect(img):
    """
    img: path, URL, or numpy array (BGR) — anything ultralytics accepts.

    Returns: list[dict], one entry per detected vehicle:
        {
            "vehicle_type": "motorcycle" | "car" | "bus" | "truck",
            "bbox": [x1, y1, x2, y2],
            "confidence": float,
            "rider_bboxes": [[x1,y1,x2,y2], ...],
            "rider_count": int,
        }
    """
    results = _model.predict(source=img, conf=CONFIDENCE_THRESHOLD, verbose=False)
    result = results[0]

    vehicles = []
    persons = []

    for box in result.boxes:
        cls_name = _model.names[int(box.cls[0])]
        confidence = float(box.conf[0])
        bbox = [round(v, 1) for v in box.xyxy[0].tolist()]

        if cls_name in VEHICLE_CLASSES:
            vehicles.append({"vehicle_type": cls_name, "bbox": bbox, "confidence": confidence})
        elif cls_name == PERSON_CLASS:
            persons.append(bbox)

    detections = []
    for vehicle in vehicles:
        if vehicle["vehicle_type"] == "motorcycle":
            rider_bboxes = [p for p in persons if _boxes_overlap_or_above(p, vehicle["bbox"])]
        else:
            rider_bboxes = []
        detections.append({**vehicle, "rider_bboxes": rider_bboxes, "rider_count": len(rider_bboxes)})

    return detections


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "test_images/street1.jpg"
    for d in detect(path):
        print(d)


def union_bbox(bbox_a, bbox_b):
    """
    Returns the smallest bbox that contains both input bboxes.
    Used to build a "union crop" (vehicle + rider together) — measured on
    real footage to embed much better than the vehicle box alone (Phase C
    fingerprint upgrade brief, 31 Aug 2026).
    """
    ax1, ay1, ax2, ay2 = bbox_a
    bx1, by1, bx2, by2 = bbox_b
    return [min(ax1, bx1), min(ay1, by1), max(ax2, bx2), max(ay2, by2)]
