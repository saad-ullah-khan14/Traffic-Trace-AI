"""Frame ingest. Mounted at /api/frames.

The hottest endpoint in the system: three phones posting continuously, faster
during a motion burst. It does as little as possible — validate, queue, return.
"""

import logging
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.api.deps import CurrentCamera
from app.schemas.frames import FrameAccepted, WorkerStats
from app.workers.frame_worker import FrameJob, worker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/frames", tags=["ingest"])

MAX_FRAME_BYTES = 8 * 1024 * 1024


@router.post("", response_model=FrameAccepted, status_code=status.HTTP_202_ACCEPTED)
async def post_frame(
    camera: CurrentCamera,
    frame: Annotated[UploadFile, File(description="JPEG from the phone camera")],
    ts: Annotated[Optional[str], Form(description="ISO 8601 capture time")] = None,
) -> FrameAccepted:
    """Accept one frame and queue it.

    Returns 202 without waiting for inference. The camera is taken from the
    X-Camera-Token header rather than a form field, so a phone can only ever
    submit frames as itself.
    """
    # Reject on the declared size before reading the body into memory. Reading
    # first would mean a malformed or hostile client could allocate the full
    # payload on a laptop that is also running the model.
    if frame.size is not None and frame.size > MAX_FRAME_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Frame exceeds {MAX_FRAME_BYTES // (1024 * 1024)} MB",
        )

    payload = await frame.read()

    if not payload:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty frame")
    # Checked again: size is client-declared and may be absent or a lie.
    if len(payload) > MAX_FRAME_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Frame exceeds {MAX_FRAME_BYTES // (1024 * 1024)} MB",
        )

    accepted = worker.submit(
        FrameJob(camera_id=camera["id"], ts=_parse_ts(ts), frame_bytes=payload)
    )

    return FrameAccepted(
        accepted=accepted,
        queued=worker.queue.qsize(),
        camera=camera["name"],
    )


@router.get("/stats", response_model=WorkerStats)
def frame_stats() -> dict:
    """Queue depth and counters. Used by the dashboard and during the demo."""
    return worker.stats()


def _parse_ts(raw: Optional[str]) -> datetime:
    """Prefer the phone's capture time; fall back to arrival time.

    Capture time is what the space-time gate reasons about. Using arrival time
    would fold network delay into the vehicle's apparent travel time, and a
    phone retrying after a dropped connection would look like it teleported.
    """
    if not raw:
        return datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        logger.warning("unparseable ts %r, using arrival time", raw)
        return datetime.now(timezone.utc)

    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
