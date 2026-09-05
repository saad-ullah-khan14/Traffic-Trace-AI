"""Shared types between pipeline/ (AI) and api/ (backend).

⚠️ PROPOSAL. Drafted from the Checkpoint A agreement. If your implementation
differs, CHANGE IT HERE and tell Muhammad. This file is the shared contract, not
one person's decision.

Good news: the backend already tolerates common alternative field names
(box/bbox, embedding/veh_emb, conf/confidence, ...), so small differences will
not break anything. What matters is that this file matches what you return.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

# ---------------------------------------------------------------------------
# THE one shared constant. Agreed 17 Aug 2026: CLIP ViT-B/32 -> 512.
# The database enforces it with a CHECK constraint, so a wrong-sized vector is
# rejected on insert instead of quietly ranking badly for the rest of the demo.
# ---------------------------------------------------------------------------
EMBEDDING_DIM = 512

# Reachability. Your is_reachable and the backend's SQL gate must agree exactly.
MAX_SPEED_KMH = 60.0
GRACE_SECONDS = 30.0


@dataclass
class Detection:
    """One vehicle found in one frame."""

    vehicle_type: str                        # "motorcycle" | "car" | "rickshaw" | ...
    bbox: list[float]                        # [x1, y1, x2, y2] in pixels
    veh_emb: list[float]                     # EMBEDDING_DIM floats, L2-NORMALIZED
    rider_emb: Optional[list[float]] = None  # same, or None when there is no rider
    attrs: dict[str, Any] = field(default_factory=dict)   # {"color", "helmet", "rider_count"}
    violations: list[str] = field(default_factory=list)   # ["no_helmet"] or []
    confidence: Optional[float] = None       # 0.0 - 1.0


@dataclass
class FrameResult:
    """Everything found in one frame."""

    detections: list[Detection] = field(default_factory=list)


@dataclass
class MatchCandidate:
    """A past sighting the backend thinks might be the same vehicle.

    The backend has ALREADY ranked these by appearance and sends you the best 20
    (option (b), agreed at Checkpoint A). Your score_candidates fuses in the
    other signals.
    """

    sighting_id: str
    camera_id: str
    ts: datetime
    vehicle_type: str
    veh_emb: list[float]
    rider_emb: Optional[list[float]]
    attrs: dict[str, Any]
    visual_score: float                      # cosine similarity the backend computed


@dataclass
class ScoredCandidate:
    """Your verdict on one candidate."""

    sighting_id: str
    score: float                             # 0.0 - 1.0, fused
    breakdown: dict[str, float]              # {"vehicle":.., "rider":.., "attributes":.., "space_time":..}
    # breakdown keys become the score bars in the officer's review screen, so
    # whatever you put here is literally what gets drawn.
