"""Shared dependencies — the Express `middleware/` equivalent.

Injected into route handlers with Depends(...). Keeping auth here means no
route re-implements a token check, and Phase 16 hardening happens in one place.
"""

from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, status

from app.db.queries import cameras as cameras_q
from app.db.session import get_connection


def require_camera(
    x_camera_token: Annotated[str | None, Header(alias="X-Camera-Token")] = None,
) -> dict[str, Any]:
    """Resolve the calling phone from its camera token.

    Guards POST /api/frames and the location update. A phone that cannot present
    a valid token cannot write anything into the system.
    """
    if not x_camera_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Camera-Token header",
        )

    with get_connection() as conn:
        camera = cameras_q.get_camera_by_token(conn, x_camera_token)

    if camera is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unknown camera token",
        )

    return camera


CurrentCamera = Annotated[dict[str, Any], Depends(require_camera)]
