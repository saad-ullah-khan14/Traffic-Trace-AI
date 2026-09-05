from ultralytics import YOLO

def run_smoke_test():
    # Pretrained YOLO11n model load karo — pehli baar chalane pe khud download hoga
    model = YOLO("yolo11n.pt")

    # Ultralytics ka built-in sample image (bus + log stop wali photo)
    results = model.predict(source="https://ultralytics.com/images/bus.jpg", conf=0.5)

    # Detected boxes print karo
    for result in results:
        print(f"\nTotal detections: {len(result.boxes)}")
        for box in result.boxes:
            cls_id = int(box.cls[0])
            cls_name = model.names[cls_id]
            confidence = float(box.conf[0])
            coords = box.xyxy[0].tolist()
            print(f"  {cls_name}: confidence={confidence:.2f}, box={coords}")

if __name__ == "__main__":
    run_smoke_test()