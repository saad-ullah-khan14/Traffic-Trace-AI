"""
Phase 6 — process_frame orchestrator.

Combines detect() (Phase 3) + check_helmet() (Phase 4) + fingerprint()
(Phase 5) into the single function Muhammad's backend calls per frame.

Contract (confirmed against Muhammad's selftest.py):
    process_frame(image_bytes: bytes, camera_id: str, ts: str) -> dict
        {
            "detections": [
                {
                    "vehicle_type": str,
                    "bbox": [x1, y1, x2, y2],
                    "veh_emb": list[float],   # length 512, L2-normalized
                    "rider_emb": list[float] | None,
                    "attrs": dict,
                    "violations": list[str],  # e.g. ["no_helmet"], or []
                    "confidence": float,
                },
                ...
            ]
        }

Pure function — no DB, no HTTP, no network calls, per the project rules.
"""

import time

import cv2
import numpy as np

from pipeline.detector import detect, union_bbox
from pipeline.helmet import check_helmet
from pipeline.fingerprint import fingerprint_batch, _dominant_color


def _bytes_to_frame(image_bytes):
    """Decode raw image bytes (as received over HTTP) into a BGR numpy array."""
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("Could not decode image bytes — not a valid image?")
    return frame


def process_frame(image_bytes, camera_id, ts):
    """
    image_bytes: raw image bytes (e.g. from an HTTP upload), NOT a file path.
    camera_id: str
    ts: str, ISO timestamp (e.g. "2026-08-22T14:03:11Z")

    Returns a dict with a "detections" list — see module docstring for shape.

    ROBUSTNESS GUARANTEE (Phase 15): this function NEVER raises. Any
    unexpected failure is caught and logged, and an empty detections list
    is returned instead.

    SPEED NOTE (Phase 15): fingerprinting is done in ONE BATCHED call for
    all vehicles in the frame, not one call per vehicle — measured to be
    ~85% of total time when done individually.
    """
    start_time = time.time()

    try:
        frame = _bytes_to_frame(image_bytes)
    except Exception as exc:
        print(f"[process_frame] camera={camera_id} ts={ts} "
              f"FRAME DECODE FAILED: {type(exc).__name__}: {exc}")
        return {"detections": []}

    try:
        detect_start = time.time()
        raw_detections = detect(frame)
        detect_time = time.time() - detect_start
    except Exception as exc:
        print(f"[process_frame] camera={camera_id} ts={ts} "
              f"DETECT FAILED: {type(exc).__name__}: {exc}")
        return {"detections": []}

    # --- Pass 1: crop + helmet-check every detection (fast, per-item work) ---
    prepared = []
    helmet_time_total = 0.0

    for det in raw_detections:
        try:
            x1, y1, x2, y2 = [int(v) for v in det["bbox"]]
            rider_crop = None
            helmet_color = None
            violations = []

            # For motorcycles with a rider, embed the UNION of vehicle+rider
            # boxes instead of the tight vehicle box alone. Measured on real
            # footage: this alone flips the identity-matching margin from
            # negative to positive (Phase C fingerprint upgrade, 31 Aug 2026).
            embed_bbox = det["bbox"]
            if det["vehicle_type"] == "motorcycle" and det["rider_bboxes"]:
                embed_bbox = union_bbox(det["bbox"], det["rider_bboxes"][0])

            ex1, ey1, ex2, ey2 = [int(v) for v in embed_bbox]
            vehicle_crop = frame[ey1:ey2, ex1:ex2]
            if vehicle_crop.size == 0:
                continue

            if det["vehicle_type"] == "motorcycle" and det["rider_bboxes"]:
                rx1, ry1, rx2, ry2 = [int(v) for v in det["rider_bboxes"][0]]
                rider_crop = frame[ry1:ry2, rx1:rx2]

                if rider_crop.size > 0:
                    head_h = max(1, int(rider_crop.shape[0] * 0.35))
                    helmet_region = rider_crop[0:head_h, :]
                    helmet_color = _dominant_color(helmet_region)

                helmet_start = time.time()
                for rider_bbox in det["rider_bboxes"]:
                    helmet_result = check_helmet(frame, rider_bbox)
                    if helmet_result["status"] == "no_helmet":
                        violations.append("no_helmet")
                        break
                helmet_time_total += time.time() - helmet_start

            prepared.append(
                {
                    "det": det,
                    "vehicle_crop": vehicle_crop,
                    "rider_crop": rider_crop,
                    "helmet_color": helmet_color,
                    "violations": violations,
                }
            )
        except Exception as exc:
            print(f"[process_frame] camera={camera_id} ts={ts} "
                  f"SKIPPED one detection during prep: {type(exc).__name__}: {exc}")
            continue

    # --- Pass 2: fingerprint EVERYTHING in one batched CLIP call ---
    results = []
    fingerprint_time_total = 0.0

    if prepared:
        try:
            fp_start = time.time()
            vehicle_crops = [p["vehicle_crop"] for p in prepared]
            rider_crops = [p["rider_crop"] for p in prepared]
            passenger_counts = [p["det"]["rider_count"] for p in prepared]
            helmet_colors = [p["helmet_color"] for p in prepared]

            fps = fingerprint_batch(vehicle_crops, rider_crops, passenger_counts, helmet_colors)
            fingerprint_time_total = time.time() - fp_start

            for p, fp in zip(prepared, fps):
                results.append(
                    {
                        "vehicle_type": p["det"]["vehicle_type"],
                        "bbox": p["det"]["bbox"],
                        # Needed downstream to crop the RIDER into the evidence
                        # photo, not just the machine. Most bikes look alike; the
                        # person on top is what an officer actually recognises.
                        # api/app/services/ingest.py passes it to save_crop(also=).
                        # Dropped in the 31 Aug delivery and restored here: without
                        # it the evidence photo silently loses the rider, which is
                        # the opposite of the union-crop change just above.
                        "rider_bboxes": p["det"]["rider_bboxes"],
                        "veh_emb": fp["veh_emb"],
                        "rider_emb": fp["rider_emb"],
                        "attrs": fp["attrs"],
                        "violations": p["violations"],
                        "confidence": p["det"]["confidence"],
                    }
                )
        except Exception as exc:
            print(f"[process_frame] camera={camera_id} ts={ts} "
                  f"BATCH FINGERPRINT FAILED: {type(exc).__name__}: {exc}")
            results = []

    elapsed = time.time() - start_time
    print(
        f"[process_frame] camera={camera_id} ts={ts} "
        f"detections={len(results)} took={elapsed:.2f}s "
        f"(detect={detect_time:.2f}s, fingerprint={fingerprint_time_total:.2f}s, "
        f"helmet={helmet_time_total:.2f}s)"
    )

    return {"detections": results}

if __name__ == "__main__":
    # Quick manual check: python -m pipeline.orchestrator <image_path>
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else "test_images/street1.jpg"
    with open(path, "rb") as f:
        image_bytes = f.read()

    result = process_frame(image_bytes, "test-camera", "2026-08-22T14:03:11Z")
    for d in result["detections"]:
        print(
            f"{d['vehicle_type']}: bbox={d['bbox']}, "
            f"emb_len={len(d['veh_emb'])}, violations={d['violations']}"
        )