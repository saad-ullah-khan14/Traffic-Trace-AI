r"""Demo readiness check — "is this machine ready to demo?"

Read-only: it starts no servers, writes no rows, and changes no state. The one
exception is a single temp file in the evidence folder, deleted immediately;
that is the only honest way to test writability on Windows, where os.access()
lies about write permission.

Run it the night before, and again on demo morning:

    cd api
    .\.venv\Scripts\python.exe -m scripts.preflight

Exit code 0 means every critical check passed. Exit 1 means something is
broken; every FAIL line carries the exact command that fixes it.

Expect a wall of onnxruntime shape warnings while the pipeline imports — that
is fast_alpr's ONNX model loading, and it is normal.
"""

import importlib
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# --------------------------------------------------------------------------
# Result recording. Each line prints as its check completes, so if something
# hangs it is obvious which check hung.
# --------------------------------------------------------------------------

PASSED: list[str] = []
WARNED: list[str] = []
FAILED: list[str] = []


def record(ok: bool, label: str, detail: str = "", fix: str = "", critical: bool = True) -> bool:
    """Print one PASS / WARN / FAIL line. Returns ok, so callers can branch."""
    if ok:
        status, bucket = "PASS", PASSED
    elif critical:
        status, bucket = "FAIL", FAILED
    else:
        status, bucket = "WARN", WARNED

    bucket.append(label)
    line = f"  {status}  {label}"
    if detail:
        line += f"  -  {detail}"
    print(line, flush=True)
    if not ok and fix:
        print(f"        fix: {fix}", flush=True)
    return ok


def section(name: str) -> None:
    print(f"\n{name}", flush=True)


# --------------------------------------------------------------------------
# 1. Interpreter
# --------------------------------------------------------------------------

def check_python() -> None:
    section("Python")
    record(
        sys.version_info[:2] == (3, 12),
        "Python 3.12",
        f"{sys.version.split()[0]} at {sys.executable}",
        r"Wrong interpreter. From api\ run: .\.venv\Scripts\python.exe -m scripts.preflight"
        " (the machine's default python is 3.14 and has no binary wheels)",
    )


# --------------------------------------------------------------------------
# 2. Working directory and settings
#    .env is read relative to the current directory, so running from anywhere
#    but api/ produces a confusing pydantic error instead of a useful one.
# --------------------------------------------------------------------------

def check_settings():
    section("Settings")
    if Path.cwd().resolve() != (ROOT / "api").resolve():
        record(
            False,
            "run from api/",
            f"cwd is {Path.cwd()}",
            f'cd "{ROOT / "api"}"'
            r'  then  .\.venv\Scripts\python.exe -m scripts.preflight',
        )
        return None
    try:
        from app.core.config import settings
    except Exception as exc:
        record(False, "api/.env loads", f"{type(exc).__name__}: {exc}",
               "Copy api/.env.example to api/.env and fill in DATABASE_URL")
        return None

    host = settings.DATABASE_URL.split("@")[-1]  # never print the password
    record(True, "api/.env loads", f"db {host}, evidence {settings.EVIDENCE_DIR}")
    return settings


# --------------------------------------------------------------------------
# 3. Imports
#    fast_alpr matters more than it looks: pipeline/__init__.py imports alpr at
#    module load, so a missing fast_alpr breaks the ENTIRE pipeline - detection,
#    embeddings, everything - not just plate reading.
# --------------------------------------------------------------------------

IMPORTS = [
    ("fastapi", r"api\.venv\Scripts\pip install -r api\requirements.txt"),
    ("psycopg", r"api\.venv\Scripts\pip install -r api\requirements.txt"),
    ("numpy", r"api\.venv\Scripts\pip install -r api\requirements.txt"),
    ("torch", r"api\.venv\Scripts\pip install -r pipeline\requirements.txt"),
    ("ultralytics", r"api\.venv\Scripts\pip install -r pipeline\requirements.txt"),
    ("open_clip", r"api\.venv\Scripts\pip install open_clip_torch"),
    ("cv2", r"api\.venv\Scripts\pip install opencv-python"),
    ("fast_alpr", r"api\.venv\Scripts\pip install fast-alpr"
                  "   (missing -> the WHOLE pipeline fails to import, not just plates)"),
    ("onnxruntime", r"api\.venv\Scripts\pip install onnxruntime"),
]


def check_imports() -> None:
    section("Imports  (torch and fast_alpr are slow; the onnxruntime warnings are normal)")
    for name, fix in IMPORTS:
        try:
            module = importlib.import_module(name)
        except Exception as exc:
            record(False, name, f"{type(exc).__name__}: {exc}", fix)
            continue
        record(True, name, str(getattr(module, "__version__", "") or ""))


# --------------------------------------------------------------------------
# 4. The pipeline's seven functions
#    A placeholder is detectable without calling it: the real implementations
#    live in submodules, so __module__ == "pipeline" means the function is
#    still the stub defined inside pipeline/__init__.py.
#    is_reachable is the deliberate exception - it is genuinely implemented in
#    __init__.py because it is four lines long.
# --------------------------------------------------------------------------

REAL_IN_INIT = {"is_reachable"}

# dedupe is Teammate 1's outstanding Phase 14 work. Its absence degrades the
# candidate list (repeat frames of one vehicle crowd it) but nothing breaks, so
# it warns rather than fails - a preflight that always exits 1 gets ignored.
NON_CRITICAL = {"dedupe"}

PIPELINE_FUNCTIONS = [
    "process_frame",
    "read_plate",
    "score_candidates",
    "is_reachable",
    "check_watchlist",
    "build_journey",
    "dedupe",
]


def check_pipeline() -> None:
    section("Pipeline (Teammate 1's AI)")
    started = time.perf_counter()
    try:
        # Imported through the API's own boundary module, so this exercises the
        # exact path uvicorn takes, including the sys.path fix-up it performs.
        from app.services import pipeline_client
    except Exception as exc:
        record(False, "pipeline imports", f"{type(exc).__name__}: {exc}",
               "See the traceback above. A broken pipeline means every sighting is FAKE.")
        return

    elapsed = time.perf_counter() - started
    if not record(
        pipeline_client.PIPELINE_AVAILABLE,
        "pipeline is the real AI",
        f"{pipeline_client.PIPELINE_STATUS} ({elapsed:.1f}s to load)",
        "The API would invent random embeddings and every incident would be fiction. "
        "Check that pipeline/ sits beside api/ and that the imports above all pass.",
    ):
        return

    import pipeline

    for name in PIPELINE_FUNCTIONS:
        func = getattr(pipeline, name, None)
        if func is None:
            record(False, f"pipeline.{name}", "not exported",
                   "Ask Teammate 1 - it is missing from pipeline/__init__.py")
            continue
        module = getattr(func, "__module__", "?")
        is_real = module != "pipeline" or name in REAL_IN_INIT
        record(
            is_real,
            f"pipeline.{name}",
            f"real, in {module}" if is_real else "PLACEHOLDER (still defined in pipeline/__init__.py)",
            f"Ask Teammate 1 for the real {name}.",
            critical=name not in NON_CRITICAL,
        )


# --------------------------------------------------------------------------
# 5. Database
# --------------------------------------------------------------------------

TABLES = ["cameras", "sightings", "incidents", "matches", "journeys"]

# Bounds on the pairwise camera distances. Under 100 m the space-time gate
# cannot discriminate at all; over 25 km nothing is reachable inside the
# 30-minute match window at 60 km/h, so every incident would find zero
# candidates and the demo would look broken with no error anywhere.
MIN_PAIR_M = 100.0
WARN_PAIR_M = 10_000.0
MAX_PAIR_M = 25_000.0


def check_database() -> None:
    section("Database")
    try:
        from app.db.session import get_connection
        from app.services.geo import haversine_meters, min_travel_seconds
    except Exception as exc:
        record(False, "db layer imports", f"{type(exc).__name__}: {exc}", "See the traceback above")
        return

    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT current_database() AS db, version() AS v")
            info = cur.fetchone()
            cur.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            )
            present = {row["table_name"] for row in cur.fetchall()}
            cur.execute("SELECT name, lat, lng, token FROM cameras ORDER BY name")
            cameras = cur.fetchall()
    except Exception as exc:
        record(
            False,
            "database reachable",
            f"{type(exc).__name__}: {exc}",
            "Start-Service postgresql-x64-18   (then re-run). If it still fails, check "
            "DATABASE_URL in api/.env",
        )
        return

    record(True, "database reachable", f"{info['db']} on {info['v'].split(' on ')[0]}")

    missing = [t for t in TABLES if t not in present]
    record(
        not missing,
        "all 5 tables exist",
        ("missing: " + ", ".join(missing)) if missing else ", ".join(TABLES),
        r'psql -U postgres -d traffic_trace -f contracts\schema.sql',
    )
    if missing:
        return

    if not record(
        len(cameras) == 3,
        "3 cameras seeded",
        f"{len(cameras)} found",
        r".\.venv\Scripts\python.exe -m scripts.seed_cameras",
    ):
        return

    bad_coords = [c["name"] for c in cameras if not c["lat"] or not c["lng"]]
    record(
        not bad_coords,
        "camera coordinates set",
        ("at (0,0) or NULL: " + ", ".join(bad_coords)) if bad_coords else "all three positioned",
        r".\.venv\Scripts\python.exe -m scripts.seed_cameras",
    )

    record(
        all(c["token"] for c in cameras),
        "camera tokens present",
        "the phones paste these into /camera",
        r".\.venv\Scripts\python.exe -m scripts.seed_cameras",
    )

    for i, a in enumerate(cameras):
        for b in cameras[i + 1:]:
            metres = haversine_meters(a["lat"], a["lng"], b["lat"], b["lng"])
            label = f"{a['name']} -> {b['name']}"
            detail = (f"{metres / 1000:.2f} km, gate enforces a "
                      f"{min_travel_seconds(metres):.0f}s minimum gap")
            if metres < MIN_PAIR_M or metres > MAX_PAIR_M:
                record(False, label, detail,
                       "Too close to tell apart, or too far to be reachable inside the 30-minute "
                       "window - every incident would find zero candidates. Fix the coordinates in "
                       "scripts/seed_cameras.py and re-run it.")
            elif metres > WARN_PAIR_M:
                record(False, label, detail,
                       "Reachable, but only just - a slow vehicle falls outside the window.",
                       critical=False)
            else:
                record(True, label, detail)


# --------------------------------------------------------------------------
# 6. Weights, tiles, evidence, disk
# --------------------------------------------------------------------------

def check_weights() -> None:
    section("Model weights")
    for name in ("yolov8n.pt", "helmet_model.pt"):
        path = ROOT / "pipeline" / name
        exists = path.is_file()
        record(
            exists,
            f"pipeline/{name}",
            f"{path.stat().st_size / 1e6:.1f} MB" if exists else "missing",
            "Both weights are committed to the backend repo despite the *.pt ignore rule - "
            "re-pull, or copy them from the USB backup. Without them the pipeline cannot start.",
        )


def check_bench_overrides() -> None:
    """Refuse to call a machine demo-ready while a testing shortcut is on."""
    section("Bench-testing overrides")
    from app.core.constants import GATE_MAX_REQUIRED_GAP_SECONDS

    if GATE_MAX_REQUIRED_GAP_SECONDS is None:
        record(True, "reachability gate enforces real travel times",
               "no overrides active")
    else:
        record(
            False,
            "REACHABILITY GATE IS OVERRIDDEN",
            f"the gate demands at most {GATE_MAX_REQUIRED_GAP_SECONDS:.0f}s between any two "
            f"cameras, so 'a vehicle cannot be 3 km away seconds later' is NOT true right now",
            "set GATE_MAX_REQUIRED_GAP_SECONDS = None in api/app/core/constants.py",
        )


def check_tiles() -> None:
    section("Offline map tiles")
    tiles_dir = ROOT / "dashboard" / "public" / "tiles"
    files = list(tiles_dir.rglob("*.png")) if tiles_dir.is_dir() else []
    count = len(files)
    fix = (r"Remove-Item -Recurse -Force dashboard\public\tiles   then"
           r"   cd api  then  .\.venv\Scripts\python.exe -m scripts.download_tiles"
           "   - NEEDS INTERNET, so this cannot be fixed at the venue.")

    if count == 0:
        record(False, "cached tiles", "none found - the map renders as blank grey squares", fix)
        return
    if count < 200:
        record(False, "cached tiles", f"{count} tiles, thinner than the ~700 expected",
               fix, critical=False)
    else:
        record(True, "cached tiles", f"{count} tiles in {tiles_dir}")

    # Counting files is not enough, and this is not hypothetical: a provider that
    # refuses bulk downloads answers 200 with one "Access blocked" image for every
    # request. That produced 528 byte-identical files that satisfied every count
    # based check while the map rendered a wall of "Access blocked" on screen.
    # Real tiles of different ground are never all the same.
    import hashlib

    digests = {hashlib.md5(f.read_bytes()).hexdigest() for f in files}
    if len(digests) <= max(2, count // 50):
        record(False, "tiles are real map images",
               f"{count} tiles but only {len(digests)} distinct image(s) - these are "
               f"placeholder/blocked images, not a map", fix)
    else:
        record(True, "tiles are real map images", f"{len(digests)} distinct images")

    # The map centres on the cameras, so those are the tiles that must exist.
    import math

    try:
        from app.db.queries import cameras as _cams_q
        from app.db.session import get_connection

        with get_connection() as conn:
            cams = _cams_q.list_cameras(conn)
    except Exception:
        return

    def deg2tile(lat, lng, zoom):
        n = 2.0 ** zoom
        return (int((lng + 180.0) / 360.0 * n),
                int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n))

    uncovered = []
    for cam in cams:
        for zoom in range(13, 18):
            x, y = deg2tile(cam["lat"], cam["lng"], zoom)
            if not (tiles_dir / str(zoom) / str(x) / f"{y}.png").exists():
                uncovered.append(f"{cam['name']} z{zoom}")

    if uncovered:
        record(False, "every camera is inside the cached area",
               f"missing: {', '.join(uncovered[:4])}"
               + (f" (+{len(uncovered) - 4} more)" if len(uncovered) > 4 else ""),
               r"re-run download_tiles with --lat/--lng centred on the cameras", critical=False)
    elif cams:
        record(True, "every camera is inside the cached area",
               f"{len(cams)} cameras covered at zoom 13-17")


def check_evidence(settings) -> None:
    section("Evidence storage")
    evidence = Path(settings.EVIDENCE_DIR).resolve()
    probe = evidence / ".preflight_write_test"
    try:
        evidence.mkdir(parents=True, exist_ok=True)
        probe.write_bytes(b"preflight")
        probe.unlink()
    except Exception as exc:
        record(False, "evidence dir writable", f"{evidence}: {type(exc).__name__}: {exc}",
               "Every crop, and so every image in the court case file, is written here.")
        return
    crops = sum(1 for _ in evidence.glob("*.jpg"))
    record(True, "evidence dir writable", f"{evidence} ({crops} crop files on disk)")


def check_disk() -> None:
    section("Disk space")
    for drive in dict.fromkeys(["C:\\", ROOT.drive + "\\"]):  # de-duplicated, order kept
        try:
            free_gb = shutil.disk_usage(drive).free / 2**30
        except Exception as exc:
            record(False, f"{drive} free space", str(exc), "Drive unreadable", critical=False)
            continue
        if free_gb < 1:
            record(False, f"{drive} free space", f"{free_gb:.1f} GB",
                   "Under 1 GB - Postgres and Windows both misbehave here. Free space now.")
        elif free_gb < 5:
            record(False, f"{drive} free space", f"{free_gb:.1f} GB",
                   "Tight. Survivable for a 7-minute demo, but clear room if you can.",
                   critical=False)
        else:
            record(True, f"{drive} free space", f"{free_gb:.1f} GB")


# --------------------------------------------------------------------------

def main() -> int:
    print("Traffic_Trace preflight - is this machine ready to demo?")
    print("=" * 72)
    started = time.perf_counter()

    check_python()
    settings = check_settings()
    check_imports()
    check_pipeline()
    if settings is not None:
        check_database()
    check_weights()
    check_bench_overrides()
    check_tiles()
    if settings is not None:
        check_evidence(settings)
    check_disk()

    print("\n" + "=" * 72)
    print(f"{len(PASSED)} passed | {len(WARNED)} warnings | {len(FAILED)} failed"
          f"   ({time.perf_counter() - started:.1f}s)")

    if WARNED:
        print("\nWarnings - known, will not stop the demo:")
        for label in WARNED:
            print(f"  - {label}")

    if FAILED:
        print("\nNOT READY. Fix these before demo day:")
        for label in FAILED:
            print(f"  - {label}")
        print("\nEach one printed its fix above.")
        return 1

    print("\nREADY. Run start_demo.ps1 on the morning.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
