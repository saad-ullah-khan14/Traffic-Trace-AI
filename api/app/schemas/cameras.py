"""Request and response models for camera endpoints.

FastAPI generates the /docs page and all input validation from these, so the
contract in contracts/endpoints.md stays true by construction.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CameraCreate(BaseModel):
    """Register a new camera position."""

    name: str = Field(min_length=1, max_length=120, examples=["Kalma Chowk"])
    lat: float = Field(ge=-90, le=90, examples=[31.5010])
    lng: float = Field(ge=-180, le=180, examples=[74.3260])
    heading: Optional[float] = Field(
        default=None,
        ge=0,
        lt=360,
        description="Compass degrees the phone faces. Cosmetic only — draws a "
        "direction cone on the map; the matching engine ignores it.",
    )


class CameraOut(BaseModel):
    id: UUID
    name: str
    lat: float
    lng: float
    heading: Optional[float] = None
    created_at: Optional[datetime] = None


class CameraWithToken(CameraOut):
    """Returned only at registration. The token is never listed again."""

    token: str


class CameraClaim(BaseModel):
    """A phone identifying itself as an already-seeded camera."""

    token: str = Field(min_length=8, description="The camera's secret, typed on the phone")


class CameraLocation(BaseModel):
    """GPS fix reported by the phone, or a manually dragged pin."""

    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    accuracy_m: Optional[float] = Field(
        default=None,
        ge=0,
        description="Reported GPS accuracy in metres. Stored for diagnostics only.",
    )
