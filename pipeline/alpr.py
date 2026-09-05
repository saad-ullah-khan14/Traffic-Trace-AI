"""
Phase 8 — ALPR module.

read_plate(vehicle_crop) -> str | None

Reads a license plate from a vehicle crop. Returns None when unreadable
or confidence is low — an unread plate is the expected/common case in
this project (that's WHY the whole ReID system exists), while a WRONG
plate reading is actively harmful (could misidentify an innocent vehicle).
So we err heavily on the side of returning None over guessing.
"""
import logging

_logger = logging.getLogger(__name__)
from fast_alpr import ALPR

# Loaded once at import time.
_alpr = ALPR(
    detector_model="yolo-v9-t-384-license-plate-end2end",
    ocr_model="global-plates-mobile-vit-v2-model",
)

CONFIDENCE_THRESHOLD = 0.5

# Measured 2 Sep (real production-path test, 5 sample recordings): every
# plate box under this size produced a WRONG accepted read — e.g. a
# 26x15px box read as "SAD426", which was actually a different vehicle's
# plate entirely (the incident bike's own plate wasn't even in frame), and
# was unreadable to a human even at 6x zoom. A tiny/blurred box gives the
# OCR model almost nothing to work with, so its confidence number is
# meaningless at that size. No CONFIDENCE_THRESHOLD fixes this: tested up
# to 0.65, and there is no gap to tune into because there is no CORRECT
# read in the sample to separate from the wrong ones. The fix is to never
# let the OCR model see boxes this small in the first place.
MIN_PLATE_WIDTH_PX = 80
MIN_PLATE_HEIGHT_PX = 30


def read_plate(vehicle_crop):
    """
    vehicle_crop: numpy BGR image, cropped to the vehicle's bbox.

    Returns: plate text (str) if confidently read, else None.
    """
    if vehicle_crop is None or vehicle_crop.size == 0:
        return None
    if vehicle_crop.shape[0] < 20 or vehicle_crop.shape[1] < 20:
        return None

    results = _alpr.predict(vehicle_crop)

    if not results:
        return None

    # Filter out plate boxes too small to plausibly be readable, BEFORE
    # picking the "best" one — a tiny box with an artificially high average
    # confidence must never win against a real, larger plate.
    def _box_big_enough(r):
        bb = r.detection.bounding_box
        return (bb.x2 - bb.x1) >= MIN_PLATE_WIDTH_PX and (bb.y2 - bb.y1) >= MIN_PLATE_HEIGHT_PX

    results = [r for r in results if _box_big_enough(r)]
    if not results:
        _logger.info("[read_plate] all detected plate boxes below minimum size — skipped")
        return None

    # Take the highest-confidence plate detected in this crop.
    best = max(results, key=lambda r: r.ocr.confidence if r.ocr else 0.0)

    if best.ocr is None:
        return None

    conf = best.ocr.confidence
    # confidence can be a single float or a list of per-character scores —
    # handle both, using the average when it's a list.
    if isinstance(conf, (list, tuple)):
        conf = sum(conf) / len(conf) if conf else 0.0

    text = (best.ocr.text or "").strip()

    bb = best.detection.bounding_box
    box_w, box_h = bb.x2 - bb.x1, bb.y2 - bb.y1

    # Log every decision, accepted or not. A FALSE plate read is far worse than a
    # missed one: a missed plate simply hands the vehicle to this feature, which
    # is the product; a false one routes the incident to ANPR, skips fingerprint
    # matching entirely, and prints a registration number that does not exist
    # onto something presented as evidence.
    _logger.info(
        f"[read_plate] text={text!r} confidence={conf:.3f} "
        f"threshold={CONFIDENCE_THRESHOLD} box={box_w}x{box_h}px "
        f"{'ACCEPTED' if conf >= CONFIDENCE_THRESHOLD and text else 'rejected'}"
    )

    if conf < CONFIDENCE_THRESHOLD:
        return None

    if not text:
        return None

    return text


if __name__ == "__main__":
    # Quick manual check: python -m pipeline.alpr <image_path>
    import sys

    import cv2

    path = sys.argv[1] if len(sys.argv) > 1 else "test_images/street1.jpg"
    frame = cv2.imread(path)
    plate = read_plate(frame)
    print(f"Plate: {plate}")