import logging
logging.basicConfig(level=logging.INFO, format="%(message)s")

import os
import cv2
from pipeline.helmet import check_helmet

folder = "evidence"
for f in sorted(os.listdir(folder)):
    if not f.endswith(".jpg"):
        continue
    img = cv2.imread(os.path.join(folder, f))
    if img is None:
        continue
    h, w = img.shape[:2]
    # Approximate the rider as the whole crop (evidence crops are already
    # near-tight around the rider) since we don't have separate bbox data.
    rider_bbox = [0, 0, w, h]
    print(f"--- {f[:16]}... shape={img.shape} ---")
    result = check_helmet(img, rider_bbox)
    print(f"  RESULT: {result}\n")
