import logging
logging.basicConfig(level=logging.INFO, format="%(message)s")

from pipeline.detector import detect
from pipeline.alpr import read_plate
import cv2

frame = cv2.imread("tools/test_recordings/cam-A/frame_003.jpg")
detections = detect(frame)
print(f"{len(detections)} vehicle(s) detected\n")

for i, d in enumerate(detections):
    x1, y1, x2, y2 = [int(v) for v in d["bbox"]]
    crop = frame[y1:y2, x1:x2]
    print(f"--- vehicle {i} ---")
    result = read_plate(crop)
    print(f"RESULT: {result}\n")
