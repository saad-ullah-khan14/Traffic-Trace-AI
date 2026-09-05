from fast_alpr import ALPR
from pipeline.detector import detect
import cv2

alpr = ALPR(
    detector_model="yolo-v9-t-384-license-plate-end2end",
    ocr_model="global-plates-mobile-vit-v2-model",
)

frame = cv2.imread("tools/test_recordings/cam-A/frame_003.jpg")
detections = detect(frame)
print(f"{len(detections)} vehicle(s) detected")

for i, d in enumerate(detections):
    x1, y1, x2, y2 = [int(v) for v in d["bbox"]]
    crop = frame[y1:y2, x1:x2]
    print(f"\nvehicle {i}: type={d['vehicle_type']}, crop_shape={crop.shape}")
    results = alpr.predict(crop)
    if not results:
        print("  no plate box found")
        continue
    for r in results:
        bb = r.detection.bounding_box
        w, h = bb.x2 - bb.x1, bb.y2 - bb.y1
        text = r.ocr.text if r.ocr else None
        conf = r.ocr.confidence if r.ocr else None
        print(f"  plate box: {w}x{h}px, text={text}, conf={conf}")
