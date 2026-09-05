"""Request/response shapes for POST /api/search (Find Me)."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class SearchResultItem(BaseModel):
    sighting_id: UUID
    score: float
    ts: datetime
    vehicle_type: str
    crop_url: Optional[str] = None
    camera: dict


class SearchResponse(BaseModel):
    query_detections: int
    selected_index: int
    results: list[SearchResultItem]


class SearchNeedsSelection(BaseModel):
    """Returned when the uploaded photo has more than one vehicle — the
    officer must say which one they mean, we do not guess."""
    detail: str = "multiple_detections"
    detections: list[dict]