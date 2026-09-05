"""Crop images on disk, named by their SHA-256.

The filename IS the hash of the file's contents. That gives tamper-evidence for
free: re-hash the file, compare to the name and to `sightings.crop_hash`, and any
alteration shows up. This is what lets the Phase 15 case file claim the images
are the ones the system captured.

Images stay on disk rather than in Postgres — the database holds the path and the
hash, nothing more.
"""

import hashlib
import io
import logging
from pathlib import Path
from typing import Optional, Sequence

from PIL import Image

from app.core.config import settings

logger = logging.getLogger(__name__)

# Padding around a detection box, as a fraction of its size. A tight crop looks
# like a mistake to a reviewing officer; a little context reads as evidence.
CROP_PADDING = 0.08

JPEG_QUALITY = 88


def evidence_dir() -> Path:
    path = Path(settings.EVIDENCE_DIR).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_crop(
    frame_bytes: bytes,
    bbox: Sequence[float],
    also: Optional[Sequence[Sequence[float]]] = None,
) -> Optional[tuple[str, str]]:
    """Crop the detection out of the frame and store it.

    `also` is extra boxes to bring into the same crop — in practice the rider
    boxes on a motorcycle. YOLO's motorcycle box covers wheels, frame and seat
    and stops below the person, so a crop of it alone shows a machine with the
    rider's head sliced off. Most bikes of one model are indistinguishable; the
    person on top is what an officer actually recognises, and this photo is the
    thing they are asked to compare. Widening the frame to include the rider is
    the difference between a hard comparison and an obvious one.

    The stored `sightings.bbox` is unaffected — that stays the detection. Only
    the picture a human looks at gets wider.

    Returns (relative_path, sha256), or None if the image cannot be decoded.
    Identical crops collapse onto the same file, since the name is the content
    hash — dedupe comes free.
    """
    try:
        image = Image.open(io.BytesIO(frame_bytes))
        image.load()
    except Exception as exc:
        logger.error("could not decode frame: %s", exc)
        return None

    if image.mode != "RGB":
        image = image.convert("RGB")

    box = _padded_box(_union(bbox, also), image.width, image.height)
    if box is None:
        logger.warning("bbox %s is outside the %dx%d frame", list(bbox), image.width, image.height)
        return None

    buffer = io.BytesIO()
    image.crop(box).save(buffer, format="JPEG", quality=JPEG_QUALITY)
    data = buffer.getvalue()

    digest = hashlib.sha256(data).hexdigest()
    filename = f"{digest}.jpg"
    path = evidence_dir() / filename

    if not path.exists():
        path.write_bytes(data)

    return filename, digest


def verify_crop(filename: str, expected_hash: str) -> bool:
    """Re-hash a stored crop and compare. Used by the Phase 15 case file."""
    path = evidence_dir() / filename
    if not path.exists():
        return False
    return hashlib.sha256(path.read_bytes()).hexdigest() == expected_hash


def _union(
    bbox: Sequence[float], also: Optional[Sequence[Sequence[float]]]
) -> Sequence[float]:
    """Smallest box containing `bbox` and every box in `also`."""
    if not also:
        return bbox

    try:
        x1, y1, x2, y2 = (float(v) for v in bbox)
        for extra in also:
            ex1, ey1, ex2, ey2 = (float(v) for v in extra)
            x1, y1 = min(x1, ex1), min(y1, ey1)
            x2, y2 = max(x2, ex2), max(y2, ey2)
    except (ValueError, TypeError):
        # A malformed rider box must never cost us the evidence photo.
        logger.warning("malformed box in `also`: %r — cropping the vehicle alone", also)
        return bbox

    return [x1, y1, x2, y2]


def _padded_box(
    bbox: Sequence[float], width: int, height: int
) -> Optional[tuple[int, int, int, int]]:
    """Clamp a padded [x1,y1,x2,y2] to the image, or None if it has no area."""
    try:
        x1, y1, x2, y2 = (float(v) for v in bbox)
    except (ValueError, TypeError):
        logger.warning("malformed bbox: %r", bbox)
        return None

    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1

    pad_x = (x2 - x1) * CROP_PADDING
    pad_y = (y2 - y1) * CROP_PADDING

    left = max(0, int(x1 - pad_x))
    top = max(0, int(y1 - pad_y))
    right = min(width, int(x2 + pad_x))
    bottom = min(height, int(y2 + pad_y))

    if right <= left or bottom <= top:
        return None

    return left, top, right, bottom
# --- Phase 4 of FIND_ME_PLAN.md: frame recording -----------------------

import shutil
import time
from datetime import datetime, timezone

# Measured (PROBLEMS.txt PROBLEM 11): frames are 64-115 KB. At three cameras
# during an active session this is roughly 60-700 MB per hour. Delete
# anything older than this so a long-running demo never fills the disk.
FRAME_RETENTION_HOURS = 6

# C: has been down to 0.24 GB once and took model loading down with it.
# Never let frame recording be the thing that causes that again — stop
# writing frames well before the disk is actually full.
MIN_FREE_DISK_GB = 2.0


def _frames_dir() -> Path:
    # Beside evidence/, not under it — crops and full frames have very
    # different retention needs and this keeps the DELETE FROM sightings
    # cascade (which prunes evidence/*.jpg) from touching full frames.
    path = Path(settings.EVIDENCE_DIR).resolve().parent / "evidence" / "frames"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _free_space_gb(path: Path) -> float:
    usage = shutil.disk_usage(path)
    return usage.free / (1024 ** 3)


def save_frame(frame_bytes: bytes, camera_id, ts: datetime) -> Optional[str]:
    """
    Save the whole frame a sighting came from, so a Find Me result or an
    incident review can show the full scene, not just the crop.

    Returns the relative path under evidence/, or None if recording was
    skipped (disk guard tripped, or the write failed). None is the safe
    default — a missing frame_path just means "no full scene available",
    the same as before Phase 4 existed.
    """
    frames_root = _frames_dir().parent  # evidence/, for the disk check —
    # frames/ is not the whole of evidence/, but they share the same disk.
    free_gb = _free_space_gb(frames_root)
    if free_gb < MIN_FREE_DISK_GB:
        logger.warning(
            "frame recording paused: %.2f GB free on %s, floor is %.1f GB",
            free_gb, frames_root, MIN_FREE_DISK_GB,
        )
        return None

    day = ts.strftime("%Y%m%d")
    time_part = ts.strftime("%H%M%S")
    camera_dir = _frames_dir() / str(camera_id) / day
    try:
        camera_dir.mkdir(parents=True, exist_ok=True)
        file_path = camera_dir / f"{time_part}.jpg"
        # Avoid clobbering two frames in the same second at 1 fps by adding a
        # short suffix rather than overwriting silently.
        if file_path.exists():
            file_path = camera_dir / f"{time_part}_{int(time.time() * 1000) % 1000}.jpg"
        file_path.write_bytes(frame_bytes)
    except OSError as exc:
        logger.error("could not write frame: %s", exc)
        return None

    return str(file_path.relative_to(_frames_dir().parent.parent))


def prune_old_frames(now: Optional[datetime] = None) -> int:
    """
    Delete recorded frames older than FRAME_RETENTION_HOURS. Meant to be
    called on a schedule (see the retention worker) — this function does
    one pass and returns how many files it removed.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now.timestamp() - FRAME_RETENTION_HOURS * 3600
    removed = 0
    root = _frames_dir()
    if not root.exists():
        return 0
    for path in root.rglob("*.jpg"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            continue
    if removed:
        logger.info("pruned %d frame(s) older than %dh", removed, FRAME_RETENTION_HOURS)
    return removed
