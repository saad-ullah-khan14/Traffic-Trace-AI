"""
Diagnostic: how many helmet/no_helmet boxes does the model find in the WHOLE
frame, and where — regardless of whether they match a specific rider's bbox.
This tells us if the problem is (a) the model finding nothing at all, or
(b) the geometric rider-matching missing boxes that ARE there.
"""

import cv2
from pipeline.helmet import _model, CONFIDENCE_THRESHOLD
from pipeline.detector import detect

FRAMES = [
    "test_ground_truth/frame_054.jpg",
    "test_ground_truth/frame_069.jpg",
    "test_ground_truth/frame_070.jpg",
    "test_ground_truth/frame_083.jpg",
    "test_ground_truth/frame_084.jpg",
]

for path in FRAMES:
    frame = cv2.imread(path)
    print(f"\n=== {path} ===")

    detections = detect(frame)
    motorcycles = [d for d in detections if d["vehicle_type"] == "motorcycle"]
    for m in motorcycles:
        print(f"  motorcycle bbox={m['bbox']}, rider_bboxes={m['rider_bboxes']}")

    results = _model.predict(source=frame, conf=CONFIDENCE_THRESHOLD, verbose=False)
    result = results[0]
    print(f"  helmet-model found {len(result.boxes) if result.boxes is not None else 0} box(es) in WHOLE frame (conf>={CONFIDENCE_THRESHOLD}):")
    if result.boxes is not None:
        for box in result.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            xyxy = box.xyxy[0].tolist()
            cls_name = _model.names[cls_id]
            print(f"    class={cls_name} conf={conf:.3f} bbox={[round(v,1) for v in xyxy]}")
