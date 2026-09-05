"""The single boundary between our code and Teammate 1's AI.

Nothing else in api/ imports from pipeline/. That keeps one file to change at
Integration Checkpoint B instead of hunting through services and routes.

Two jobs:

1. **Fall back to a stub.** Until pipeline.process_frame exists, a stub returns
   fake-but-well-shaped detections so the whole ingest path can be built and
   tested. Phase 7 removes nothing — the real module is simply found and used.

2. **Absorb field-name differences.** His dataclass field names are not yet
   confirmed, and a mismatch (`box` vs `bbox`) fails *silently*: empty results,
   no exception. `normalize_detection` accepts the likely aliases and logs
   loudly when a required field is missing, so the failure is visible at once.
"""

import logging
import sys
from pathlib import Path
from typing import Any, Optional, Sequence

import numpy as np

from app.core.constants import EMBEDDING_DIM

logger = logging.getLogger(__name__)


# --- locating the real pipeline ------------------------------------------------

# pipeline/ is a sibling of api/, and uvicorn runs from api/, so the repo root
# is not importable by default. Adding it here rather than requiring PYTHONPATH
# to be set keeps the run command in the README a single line.
_REPO_ROOT = str(Path(__file__).resolve().parents[3])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

try:  # pragma: no cover - depends on Teammate 1's delivery
    from pipeline import process_frame as _real_process_frame  # type: ignore
    from pipeline.fingerprint import fingerprint as _real_fingerprint  # type: ignore

    PIPELINE_AVAILABLE = True
    PIPELINE_STATUS = "real pipeline loaded"
    logger.info("pipeline.process_frame loaded — running with the real AI")
except ModuleNotFoundError:
    # Expected until Integration Checkpoint B: pipeline/ has not been delivered.
    _real_process_frame = None
    _real_fingerprint = None
    PIPELINE_AVAILABLE = False
    PIPELINE_STATUS = "stub (pipeline module not present)"
    logger.warning(
        "pipeline/ not found — using the STUB. Sightings are randomly generated "
        "and mean nothing. This is expected before Phase 7."
    )
except Exception as exc:
    # The module exists but blew up on import. Falling back silently here would
    # produce green counters and plausible-looking incidents built entirely from
    # random data — the worst possible failure at Checkpoint B. Make it loud.
    _real_process_frame = None
    _real_fingerprint = None
    PIPELINE_AVAILABLE = False
    PIPELINE_STATUS = f"stub (pipeline import FAILED: {exc})"
    logger.error(
        "pipeline/ EXISTS BUT FAILED TO IMPORT: %s. Falling back to the stub — "
        "every sighting from now on is FAKE. Fix the import before trusting any "
        "result on screen.",
        exc,
        exc_info=True,
    )


# --- field-name tolerance ------------------------------------------------------

# First name that exists wins. Extend when Teammate 1 confirms his dataclasses.
_ALIASES: dict[str, tuple[str, ...]] = {
    "vehicle_type": ("vehicle_type", "vehicleType", "type", "cls", "label", "category"),
    "bbox": ("bbox", "box", "bounding_box", "boundingBox", "xyxy", "rect"),
    "veh_emb": ("veh_emb", "vehicle_embedding", "vehicle_emb", "embedding", "emb", "feat"),
    "rider_emb": ("rider_emb", "rider_embedding", "person_emb", "rider_feat"),
    "rider_bboxes": ("rider_bboxes", "rider_boxes", "riders", "person_bboxes"),
    "attrs": ("attrs", "attributes", "meta", "properties"),
    "violations": ("violations", "violation", "flags", "offenses"),
    "confidence": ("confidence", "conf", "score", "det_score"),
}


def _pluck(source: Any, names: Sequence[str]) -> Any:
    """First present attribute or key, trying each alias in order."""
    for name in names:
        if isinstance(source, dict):
            if name in source:
                return source[name]
        elif hasattr(source, name):
            return getattr(source, name)
    return None


def normalize_detection(raw: Any) -> Optional[dict[str, Any]]:
    """Coerce one detection into the shape the ingest service expects.

    Returns None and logs if a required field is missing, so one malformed
    detection cannot abort a whole frame.
    """
    vehicle_type = _pluck(raw, _ALIASES["vehicle_type"])
    bbox = _pluck(raw, _ALIASES["bbox"])
    veh_emb = _pluck(raw, _ALIASES["veh_emb"])

    missing = [
        label
        for label, value in (
            ("vehicle_type", vehicle_type),
            ("bbox", bbox),
            ("veh_emb", veh_emb),
        )
        if value is None
    ]
    if missing:
        available = sorted(raw.keys()) if isinstance(raw, dict) else sorted(
            a for a in dir(raw) if not a.startswith("_")
        )
        logger.error(
            "detection missing required field(s) %s. Fields present: %s. "
            "Add the correct alias to _ALIASES in pipeline_client.py.",
            missing,
            available,
        )
        return None

    # Check the dimension here rather than letting the DB CHECK constraint catch
    # it. A constraint violation aborts the whole frame's transaction, losing
    # sightings that already inserted, and surfaces as a raw psycopg error.
    # Dropping one malformed detection keeps the rest of the frame.
    veh_emb = list(veh_emb)
    if len(veh_emb) != EMBEDDING_DIM:
        logger.error(
            "detection has a %d-dimension embedding, expected %d. Dropping it. "
            "Check EMBEDDING_DIM agrees with pipeline/types.py.",
            len(veh_emb),
            EMBEDDING_DIM,
        )
        return None

    rider_emb = _listify(_pluck(raw, _ALIASES["rider_emb"]))
    if rider_emb is not None and len(rider_emb) != EMBEDDING_DIM:
        logger.warning(
            "rider_emb has %d dimensions, expected %d — storing without it.",
            len(rider_emb),
            EMBEDDING_DIM,
        )
        rider_emb = None

    violations = _pluck(raw, _ALIASES["violations"]) or []
    if isinstance(violations, str):
        violations = [violations]

    return {
        "vehicle_type": str(vehicle_type),
        "bbox": [float(v) for v in bbox],
        "veh_emb": veh_emb,
        "rider_emb": rider_emb,
        "rider_bboxes": [
            [float(v) for v in box]
            for box in (_pluck(raw, _ALIASES["rider_bboxes"]) or [])
        ],
        "attrs": _pluck(raw, _ALIASES["attrs"]) or {},
        "violations": list(violations),
        "confidence": _floatify(_pluck(raw, _ALIASES["confidence"])),
    }


def _listify(value: Any) -> Optional[list]:
    return None if value is None else list(value)


def _floatify(value: Any) -> Optional[float]:
    return None if value is None else float(value)


def extract_detections(result: Any) -> list[dict[str, Any]]:
    """Pull the detection list out of whatever process_frame returned.

    Accepts a FrameResult-like object, a dict, or a bare list.
    """
    if result is None:
        return []

    raw_list = result if isinstance(result, list) else _pluck(
        result, ("detections", "sightings", "results", "items", "objects")
    )
    if raw_list is None:
        logger.error(
            "process_frame result has no detections list. Type=%s", type(result).__name__
        )
        return []

    return [d for d in (normalize_detection(r) for r in raw_list) if d is not None]


# --- the stub ------------------------------------------------------------------

_STUB_VEHICLES = ["motorcycle", "car", "rickshaw"]
_stub_rng = np.random.default_rng()


def _stub_process_frame(image_bytes: bytes, camera_id: str, ts: Any) -> dict[str, Any]:
    """Fake detections with the right shape, so ingest can be built and tested.

    Embeddings are L2-normalized here because the real process_frame will be —
    testing against unnormalized vectors would hide bugs that only appear later.

    Roughly one frame in four carries a no-helmet violation, so incidents appear
    often enough to exercise the flow without flooding it.
    """
    count = int(_stub_rng.integers(1, 3))
    detections = []

    for _ in range(count):
        vec = _stub_rng.standard_normal(EMBEDDING_DIM).astype(np.float32)
        vec /= np.linalg.norm(vec)

        x1 = float(_stub_rng.integers(0, 300))
        y1 = float(_stub_rng.integers(0, 200))
        has_violation = bool(_stub_rng.random() < 0.25)

        detections.append(
            {
                "vehicle_type": str(_stub_rng.choice(_STUB_VEHICLES)),
                "bbox": [x1, y1, x1 + 120.0, y1 + 160.0],
                "veh_emb": vec.tolist(),
                "rider_emb": None,
                "attrs": {
                    "color": str(_stub_rng.choice(["red", "black", "white", "blue"])),
                    "helmet": not has_violation,
                    "rider_count": int(_stub_rng.integers(1, 3)),
                    "stub": True,
                },
                "violations": ["no_helmet"] if has_violation else [],
                "confidence": round(float(_stub_rng.uniform(0.6, 0.99)), 3),
            }
        )

    return {"detections": detections}


def process_frame(image_bytes: bytes, camera_id: str, ts: Any) -> list[dict[str, Any]]:
    """Call the real pipeline if present, otherwise the stub. Always normalized."""
    if PIPELINE_AVAILABLE and _real_process_frame is not None:
        return extract_detections(_real_process_frame(image_bytes, camera_id, ts))
    return extract_detections(_stub_process_frame(image_bytes, camera_id, ts))


def read_plate(image_bytes: bytes, bbox: Sequence[float]) -> Optional[str]:
    """Plate text, or None when unreadable.

    Teammate 1's signature is read_plate(vehicle_crop) — a cropped BGR array,
    not the whole frame — so the crop is done here. cv2 rather than PIL because
    the rest of pipeline/ works in BGR, and handing it RGB would swap the
    channels and quietly wreck OCR.

    Returns None until his Phase 8 lands. That is also the correct demo
    behaviour: an unreadable plate is the case this product exists for.
    """
    if not PIPELINE_AVAILABLE:
        return None

    try:
        import cv2
        import numpy as np

        from pipeline import read_plate as _real_read_plate  # type: ignore

        frame = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            return None

        x1, y1, x2, y2 = (int(v) for v in bbox)
        crop = frame[max(0, y1):max(0, y2), max(0, x1):max(0, x2)]
        if crop.size == 0:
            return None

        return _real_read_plate(crop)
    except Exception as exc:
        logger.warning("pipeline.read_plate failed (%s); treating plate as unreadable", exc)
        return None


def score_candidates(incident: dict, candidates: list[dict]) -> list[dict]:
    """Fuse the remaining signals over our pre-ranked top-K.

    Returns [] if the pipeline is absent or raises — the caller falls back to
    plain visual ranking rather than showing the officer an empty screen.
    """
    if not PIPELINE_AVAILABLE:
        return []
    try:
        from pipeline import score_candidates as _real_score  # type: ignore

        return _real_score(incident, candidates) or []
    except Exception as exc:
        logger.error("pipeline.score_candidates failed: %s", exc, exc_info=True)
        return []


def build_journey(confirmed_sightings: list[dict]) -> Optional[dict]:
    """Chain confirmed sightings into an ordered route. None if unavailable."""
    if not PIPELINE_AVAILABLE:
        return None
    try:
        from pipeline import build_journey as _real_build  # type: ignore

        return _real_build(confirmed_sightings)
    except Exception as exc:
        logger.error("pipeline.build_journey failed: %s", exc, exc_info=True)
        return None


def check_watchlist(new_sighting: dict, open_incidents: list[dict]) -> list[dict]:
    """Does this new sighting match an already-open incident? [] if unavailable."""
    if not PIPELINE_AVAILABLE or not open_incidents:
        return []
    try:
        from pipeline import check_watchlist as _real_check  # type: ignore

        return _real_check(new_sighting, open_incidents) or []
    except Exception as exc:
        logger.error("pipeline.check_watchlist failed: %s", exc, exc_info=True)
        return []


def dedupe(new_sightings: list[dict], recent_sightings: list[dict]) -> list[dict]:
    """Collapse a burst of near-identical frames of one vehicle to its best shot.

    Returns new_sightings unchanged if the pipeline is absent or raises —
    storing a duplicate is far cheaper than dropping a real vehicle.
    """
    if not PIPELINE_AVAILABLE:
        return new_sightings
    try:
        from pipeline import dedupe as _real_dedupe  # type: ignore

        return _real_dedupe(new_sightings, recent_sightings)
    except Exception as exc:
        logger.error("pipeline.dedupe failed: %s", exc, exc_info=True)
        return new_sightings

def fingerprint(vehicle_crop) -> dict:
    """
    Direct embed of a crop, bypassing detection — for cases like a Find Me
    query photo that is ALREADY a tight crop (e.g. re-uploading an
    evidence/ file), where the detector expects a full street scene and
    often finds nothing on a pre-cropped, zoomed-in image.

    Only crossing point into pipeline/ for this, same rule as process_frame —
    nothing else in api/ imports from pipeline/ directly.
    """
    if not PIPELINE_AVAILABLE or _real_fingerprint is None:
        # Stub: a random-but-valid-shaped fingerprint, same spirit as
        # _stub_process_frame — plausible shape, meaningless content.
        import numpy as np
        vec = np.random.default_rng().standard_normal(EMBEDDING_DIM).astype(np.float32)
        vec /= np.linalg.norm(vec)
        return {"veh_emb": vec.tolist(), "rider_emb": None, "attrs": {"stub": True}}
    return _real_fingerprint(vehicle_crop)
