"""System health. Mounted at /api/health."""

from fastapi import APIRouter

from app.db.session import get_connection
from app.services.pipeline_client import PIPELINE_AVAILABLE, PIPELINE_STATUS

router = APIRouter(tags=["system"])


@router.get("/health", summary="API liveness plus a real Postgres round-trip")
def health() -> dict:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Aliased and read by key: the pool uses dict_row, so rows are
                # dicts and tuple-unpacking them would yield column names.
                cur.execute(
                    "SELECT version() AS version, current_database() AS database"
                )
                row = cur.fetchone()
        db = {
            "ok": True,
            "database": row["database"],
            "version": row["version"].split(" on ")[0],
        }
    except Exception as exc:  # reported in the response, never swallowed
        db = {"ok": False, "error": str(exc)}

    # Surfaced here so "why are the results nonsense?" is answerable in one
    # request. A silent stub fallback produces confident, entirely fake data.
    return {
        "status": "ok" if db["ok"] else "degraded",
        "db": db,
        "pipeline": {"real": PIPELINE_AVAILABLE, "status": PIPELINE_STATUS},
    }
