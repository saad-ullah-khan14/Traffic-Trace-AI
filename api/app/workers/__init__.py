"""Background work that runs outside the request/response cycle.

    frame_worker.py   consumes the asyncio queue fed by POST /api/frames (Phase 5)
    retention.py      deletes unlinked sightings after 48h                (Phase 16)

POST /api/frames must return immediately after queueing — a phone waiting on
AI inference would stall its capture loop and drop frames.
"""
