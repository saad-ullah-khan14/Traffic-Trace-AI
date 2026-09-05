"""Camera registration and positioning. Mounted at /api/cameras.

The demo flow, decided 18 Aug 2026:

    1. scripts/seed_cameras.py creates the 3 cameras, each with a secret token
    2. the phone opens /camera and the operator types that camera's secret
    3. POST /api/cameras/claim validates it — this phone is now that camera
    4. PATCH /api/cameras/me/location sends the GPS fix, or a dragged pin

POST /api/cameras exists for creating a camera that was not seeded.
"""

import logging
import secrets

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentCamera
from app.db.queries import cameras as cameras_q
from app.db.session import get_connection
from app.schemas.cameras import (
    CameraClaim,
    CameraCreate,
    CameraLocation,
    CameraOut,
    CameraWithToken,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cameras", tags=["cameras"])


@router.post("", response_model=CameraWithToken, status_code=status.HTTP_201_CREATED)
def create_camera(payload: CameraCreate) -> dict:
    """Register a camera and issue its secret token.

    The token is returned exactly once. Nothing else in the API ever discloses
    it, so it cannot be recovered from a listing — reseed or re-register instead.
    """
    with get_connection() as conn:
        camera = cameras_q.insert_camera(
            conn,
            name=payload.name,
            lat=payload.lat,
            lng=payload.lng,
            heading=payload.heading,
            token=secrets.token_urlsafe(24),
        )
    logger.info("camera registered: %s (%s)", camera["name"], camera["id"])
    return camera


@router.post("/claim", response_model=CameraOut)
def claim_camera(payload: CameraClaim) -> dict:
    """A phone identifying itself by typing a camera's secret.

    Deliberately returns the same 401 for an unknown token as the header guard,
    so a wrong secret cannot be distinguished from a disabled camera.
    """
    with get_connection() as conn:
        camera = cameras_q.get_camera_by_token(conn, payload.token)

    if camera is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unknown camera token",
        )

    logger.info("camera claimed: %s (%s)", camera["name"], camera["id"])
    return camera


@router.patch("/me/location", response_model=CameraOut)
def update_my_location(payload: CameraLocation, camera: CurrentCamera) -> dict:
    """Set this camera's position from a GPS fix or a manually dragged pin.

    Identified by the X-Camera-Token header rather than an id in the path, so a
    phone can only ever move itself.

    Position is not cosmetic — it feeds the reachability gate, so a bad fix
    widens or narrows which past sightings count as reachable. That is why the
    phone page must offer a manual drag as a fallback.
    """
    with get_connection() as conn:
        updated = cameras_q.update_camera_location(
            conn, camera_id=camera["id"], lat=payload.lat, lng=payload.lng
        )

    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")

    logger.info(
        "camera %s moved to %.6f, %.6f (accuracy %s m)",
        updated["name"],
        payload.lat,
        payload.lng,
        payload.accuracy_m,
    )
    return updated


@router.get("", response_model=list[CameraOut])
def list_cameras() -> list[dict]:
    """All cameras, for the live map and the phone's camera picker. No tokens."""
    with get_connection() as conn:
        return cameras_q.list_cameras(conn)
