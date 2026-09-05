"""Traffic_Trace API — application entry point.

This file only assembles the app: settings, middleware, routers. All logic
lives in services/, all SQL in db/, all endpoints in api/routes/.

Run from the api/ directory:
    .\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

import asyncio
import logging
from logging.handlers import RotatingFileHandler
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.api.routes import ws
from app.core.config import settings
from app.db.session import close_pool, open_pool

from app.workers import retention
from app.services import evidence
from app.workers.frame_worker import worker


async def _prune_frames_forever() -> None:
    """
    Phase 4 of FIND_ME_PLAN.md's retention requirement, for the frame
    recorder. Same shape as retention.run_forever() — a periodic sweep
    that must never take the API down if it fails.
    """
    while True:
        try:
            await asyncio.to_thread(evidence.prune_old_frames)
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.getLogger(__name__).exception("frame prune sweep failed")
        await asyncio.sleep(60 * 60)  # once an hour, same cadence as retention.py


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open the connection pool on startup, close it on shutdown.

    Connecting per request costs ~15 ms on Windows — a third of the matching
    engine's latency budget spent before any work happens.
    """
    open_pool()
    worker.start()
    sweeper = asyncio.create_task(retention.run_forever(), name="retention")
    frame_pruner = asyncio.create_task(_prune_frames_forever(), name="frame-retention")
    yield
    sweeper.cancel()
    frame_pruner.cancel()
    await worker.stop()
    close_pool()


def create_app() -> FastAPI:
    # uvicorn configures only its own loggers, so without this the app's own
    # INFO lines — incidents opened, watchlist hits, candidate counts — are
    # invisible. During a demo those lines are the only way to see what the
    # system is actually doing.
    # A file handler as well as the console. The console lives in a window that
    # is closed at the end of the day, and the lines that explain a bad run —
    # how many detections were too small, what dedupe collapsed, which plate was
    # accepted — are exactly the ones needed afterwards. Rotating so a long
    # session cannot fill the disk.
    log_dir = Path(__file__).resolve().parents[2] / "logs"
    log_dir.mkdir(exist_ok=True)
    file_handler = RotatingFileHandler(
        log_dir / "api.log", maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(), file_handler],
        # force=True because uvicorn has already configured the root logger by
        # this point, and basicConfig is a no-op once handlers exist.
        force=True,
    )

    app = FastAPI(
        lifespan=lifespan,
        title="Traffic_Trace API",
        description=(
            "No-plate vehicle tracking. Every vehicle at every camera is fingerprinted; "
            "violations open incidents that are matched against past sightings."
        ),
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.CORS_ORIGIN_REGEX,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)
    # Mounted on the app, not api_router: the contract puts it at /ws/live,
    # outside the /api prefix.
    app.include_router(ws.router)

    # Crop images are served straight off disk rather than through the database.
    # Filenames are the SHA-256 of the file contents, so a URL doubles as an
    # integrity check — that is what makes the Phase 15 case file credible.
    evidence_dir = Path(settings.EVIDENCE_DIR).resolve()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/evidence", StaticFiles(directory=evidence_dir), name="evidence")

    return app


app = create_app()