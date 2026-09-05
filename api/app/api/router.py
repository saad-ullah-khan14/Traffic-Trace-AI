"""Single place where every route module is mounted.

Adding an endpoint means: write app/api/routes/<thing>.py, then include it here.
Nothing else in the app changes.
"""

from fastapi import APIRouter

from app.api.routes import admin, cameras, frames, health, incidents, journeys, matches, search
api_router = APIRouter(prefix="/api")

api_router.include_router(health.router)
api_router.include_router(cameras.router)
api_router.include_router(frames.router)
api_router.include_router(incidents.router)
api_router.include_router(matches.router)
api_router.include_router(journeys.router)
api_router.include_router(admin.router)
api_router.include_router(search.router)

