"""Response models for the incident feed and the review screen."""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel


class CameraRef(BaseModel):
    id: UUID
    name: str
    lat: Optional[float] = None
    lng: Optional[float] = None


class SightingOut(BaseModel):
    id: UUID
    ts: datetime
    vehicle_type: str
    attrs: dict[str, Any] = {}
    confidence: Optional[float] = None
    crop_url: Optional[str] = None
    crop_hash: Optional[str] = None
    camera: CameraRef


class IncidentListItem(BaseModel):
    id: UUID
    violation: str
    plate_text: Optional[str] = None
    status: str
    created_at: datetime
    vehicle_type: str
    crop_url: Optional[str] = None
    camera: CameraRef
    match_count: int


class MatchOut(BaseModel):
    id: UUID
    score: float
    # Whatever pipeline.score_candidates puts here becomes the score bars in the
    # review UI, so the keys are deliberately not fixed.
    breakdown: dict[str, float] = {}
    decision: Optional[str] = None
    decided_at: Optional[datetime] = None
    sighting: SightingOut


class IncidentDetail(BaseModel):
    id: UUID
    violation: str
    plate_text: Optional[str] = None
    status: str
    created_at: datetime
    sighting: SightingOut
    matches: list[MatchOut] = []


class DecisionIn(BaseModel):
    decision: str  # "confirm" | "reject"


class DecisionOut(BaseModel):
    id: UUID
    incident_id: UUID
    sighting_id: UUID
    decision: str
    decided_at: datetime
