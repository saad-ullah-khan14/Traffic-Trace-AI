"""Background frame processing.

POST /api/frames must answer immediately. A phone that waits for AI inference
before sending its next frame stops being a camera and becomes a bottleneck — at
1 frame per 2 seconds, even 500 ms of inference visibly degrades the capture
loop, and during a motion burst it drops frames outright.

So the endpoint validates, queues, and returns 202. This module drains the queue.

The queue is **bounded**, and when full the *oldest* frame is evicted to make
room for the newest. Memory stays flat and the system keeps processing what is
happening now rather than working through a backlog of stale empty-street
frames. Drops are counted and exposed at /api/frames/stats.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID

from app.core.events import publish
from app.db.session import get_connection
from app.services.ingest import ingest_frame

logger = logging.getLogger(__name__)

# Deliberately shallow. The queue is a *latency* budget, not storage: a frame
# waits (queue depth / throughput) before it is looked at. Measured on this
# laptop the worker sustains ~1.2 frames/s, so 64 was a **54-second** buffer.
# With three phones on a busy road the queue sat at 54/64 within 30 seconds, and
# a violation frame posted at that moment was evicted by newer arrivals before it
# ever reached the head — the incident never appeared at all. At 8 the buffer is
# ~7 seconds: more frames are dropped, but the ones that survive are recent, and
# the bike is in shot for several frames so one gets through promptly.
#
# This is what the eviction policy below was always for; the size just did not
# deliver it. Raise it only if the worker gets materially faster.
QUEUE_MAXSIZE = 8


@dataclass(slots=True)
class FrameJob:
    camera_id: UUID
    ts: datetime
    frame_bytes: bytes


class FrameWorker:
    """Owns the queue and the consumer task."""

    def __init__(self, maxsize: int = QUEUE_MAXSIZE) -> None:
        self.queue: asyncio.Queue[FrameJob] = asyncio.Queue(maxsize=maxsize)
        self._task: Optional[asyncio.Task] = None
        self.processed = 0
        self.dropped = 0
        self.failed = 0
        self.skipped = 0  # detections whose crop could not be saved

    # --- producer side ---------------------------------------------------

    def submit(self, job: FrameJob) -> bool:
        """Queue a frame, evicting the OLDEST if the queue is full.

        Returns False when an eviction happened.

        Which end to drop matters. A full queue means inference is behind, and
        the frames that matter are the ones being captured right now — during a
        motion burst, that is the vehicle committing the violation. Dropping the
        incoming frame instead would fill the queue with stale empty-street
        frames and discard the event itself.
        """
        evicted = False
        while True:
            try:
                self.queue.put_nowait(job)
                return not evicted
            except asyncio.QueueFull:
                try:
                    self.queue.get_nowait()
                    self.queue.task_done()
                    self.dropped += 1
                    evicted = True
                except asyncio.QueueEmpty:  # drained concurrently; retry
                    continue

                if self.dropped % 10 == 1:  # log the first, then every tenth
                    logger.warning(
                        "frame queue full (%d) — evicting oldest frames, inference "
                        "is behind. total dropped=%d",
                        self.queue.maxsize,
                        self.dropped,
                    )

    # --- lifecycle -------------------------------------------------------

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="frame-worker")
            logger.info("frame worker started (queue max %d)", self.queue.maxsize)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            logger.info(
                "frame worker stopped — processed=%d dropped=%d failed=%d",
                self.processed,
                self.dropped,
                self.failed,
            )

    # --- consumer side ---------------------------------------------------

    async def _run(self) -> None:
        while True:
            job = await self.queue.get()
            try:
                # psycopg and PIL are blocking; a thread keeps the event loop
                # free to accept the next frame while this one is processed.
                summary = await asyncio.to_thread(self._process, job)
                self.processed += 1

                # Broadcast on the event loop, after the threaded DB work.
                # Publishing from inside the thread would need a loop handle
                # and buy nothing — the rows are already committed by here.
                self.skipped += summary.get("skipped", 0)

                for event_type, payload in summary["events"]:
                    await publish(event_type, payload)
                # Log EVERY frame, not only the ones that open an incident.
                # Logging only the interesting frames means a run that produces
                # nothing produces no explanation either: on 1 Sep about seventy
                # frames were ingested and the log was completely silent, so
                # there was no way to tell whether the camera saw no motorcycle,
                # or saw one and every filter downstream discarded it. The whole
                # funnel goes on one line, in order.
                logger.info(
                    "frame from camera %s -> %d detected, %d kept, %d violation(s), "
                    "%d sighting(s), %d incident(s)",
                    job.camera_id,
                    summary.get("detections", 0),
                    summary.get("kept", 0),
                    summary.get("violations", 0),
                    len(summary["sightings"]),
                    len(summary["incidents"]),
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                self.failed += 1
                # One bad frame must never kill the worker — the demo would
                # silently stop ingesting with everything still looking alive.
                logger.exception("failed to process frame from camera %s", job.camera_id)
            finally:
                self.queue.task_done()

    @staticmethod
    def _process(job: FrameJob) -> dict:
        with get_connection() as conn:
            return ingest_frame(conn, job.camera_id, job.ts, job.frame_bytes)

    # --- introspection ---------------------------------------------------

    def stats(self) -> dict[str, int]:
        return {
            "queued": self.queue.qsize(),
            "queue_max": self.queue.maxsize,
            "processed": self.processed,
            "dropped": self.dropped,
            "failed": self.failed,
            "skipped": self.skipped,
        }


# One worker per process. The API runs as a single uvicorn process by design.
worker = FrameWorker()
