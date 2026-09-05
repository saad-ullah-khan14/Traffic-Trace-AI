"""
Problem 4 measurement — real ground-truth crops from actual street video,
visually verified by hand. All 5 are confirmed NO_HELMET riders (bare head,
dupatta, or prayer cap — none is a helmet).

This is the exact kind of case Muhammad's Problem 4 report described:
challenging real riders, not synthetic stock photos.
"""

import cv2
import logging
logging.basicConfig(level=logging.INFO, format="%(message)s")

from pipeline.detector import detect
from pipeline.helmet import check_helmet

# All 5 frames: EVERY rider visible is confirmed, by eye, to have NO HELMET.
FRAMES = [
    "test_ground_truth/frame_054.jpg",  # woman + child, dupatta, no helmet
    "test_ground_truth/frame_069.jpg",  # elderly man, white prayer cap, no helmet
    "test_ground_truth/frame_070.jpg",  # same elderly man, different angle
    "test_ground_truth/frame_083.jpg",  # red-shirt rider, no helmet
    "test_ground_truth/frame_084.jpg",  # same red-shirt rider + pillion, clearest frame
]

total_riders = 0
correct = 0
wrong = 0
unknown = 0

for path in FRAMES:
    frame = cv2.imread(path)
    if frame is None:
        print(f"COULD NOT READ: {path}")
        continue

    print(f"\n=== {path} ===")
    detections = detect(frame)
    motorcycles = [d for d in detections if d["vehicle_type"] == "motorcycle"]

    if not motorcycles:
        print("  No motorcycle detected at all!")
        continue

    for m in motorcycles:
        if not m["rider_bboxes"]:
            print(f"  Motorcycle detected but NO rider attached (rider_count=0) — detection miss")
            continue
        for i, rider_bbox in enumerate(m["rider_bboxes"]):
            total_riders += 1
            result = check_helmet(frame, rider_bbox)
            status = result["status"]
            conf = result["confidence"]

            if status == "no_helmet":
                verdict = "CORRECT"
                correct += 1
            elif status == "unknown":
                verdict = "MISSED (said unknown, ground truth is no_helmet)"
                unknown += 1
            else:  # "helmet"
                verdict = "WRONG — DANGEROUS FALSE NEGATIVE (said helmet, ground truth is no_helmet)"
                wrong += 1

            print(f"  rider {i}: status={status!r} confidence={conf:.3f}  -> {verdict}")

print("\n" + "=" * 60)
print(f"Total confirmed no_helmet riders tested: {total_riders}")
print(f"  Correctly flagged as no_helmet: {correct}")
print(f"  Missed (returned unknown):       {unknown}")
print(f"  WRONG (returned helmet):         {wrong}")
if total_riders:
    print(f"\nRecall on no_helmet cases: {correct}/{total_riders} = {100*correct/total_riders:.0f}%")
