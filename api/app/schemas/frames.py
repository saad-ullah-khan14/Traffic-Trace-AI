"""Response models for the ingest endpoint."""

from pydantic import BaseModel, Field


class FrameAccepted(BaseModel):
    """Returned immediately after queueing — before any AI runs."""

    accepted: bool = Field(description="False means the frame was dropped under backpressure")
    queued: int = Field(description="Frames currently waiting to be processed")
    camera: str


class WorkerStats(BaseModel):
    queued: int
    queue_max: int
    processed: int
    dropped: int
    failed: int
    skipped: int = 0
