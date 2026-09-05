from dataclasses import dataclass, field
from datetime import datetime

# Sab jagah embedding dimension yahi ek constant se aayega
EMBEDDING_DIM = 512  # CLIP ViT-B/32

@dataclass
class Detection:
    vehicle_type: str          # "motorcycle" | "car" | "rickshaw" | "truck"
    bbox: list                 # [x1, y1, x2, y2] pixels
    confidence: float          # 0.0 to 1.0
    rider_bbox: list | None = None   # attached rider ka box, agar hai to

@dataclass
class Fingerprint:
    veh_emb: list              # length EMBEDDING_DIM
    rider_emb: list | None     # length EMBEDDING_DIM, ya None agar rider nahi
    attrs: dict                # {"color": "red", "helmet": False, "rider_count": 2}

@dataclass
class Sighting:
    camera_id: str
    timestamp: datetime
    detection: Detection
    fingerprint: Fingerprint

@dataclass
class Violation:
    sighting: Sighting
    violation_type: str        # e.g. "no_helmet"
    plate_text: str | None     # None = unreadable

@dataclass
class FrameResult:
    sightings: list            # list[Sighting]
    violations: list           # list[Violation]

@dataclass
class MatchCandidate:
    sighting: Sighting
    score: float
    breakdown: dict            # {"veh_sim": 0.8, "rider_sim": 0.6, "attr": 0.9, "spacetime": 1.0}

@dataclass
class Journey:
    sightings: list            # time-ordered list[Sighting]
    total_span_seconds: float
    total_distance_km: float