# api/ — backend

FastAPI. The only code in this project that touches the database or the network.

## Layered architecture

Mapped from Express, since that's the familiar equivalent:

| Express | Here | Rule |
|---|---|---|
| `routes/` | `app/api/routes/` | URL → function. Thin: validate input, call a service, return |
| `controllers/`, `services/` | `app/services/` | All business logic and workflow |
| `middleware/` | `app/api/deps.py` | Shared guards via `Depends` — camera tokens, officer PIN |
| `models/` | `app/db/queries/` | **All SQL lives here. Nowhere else.** |
| Joi / Zod | `app/schemas/` | Pydantic request/response models |
| `config/` | `app/core/` | Settings, security, event bus |
| — | `app/workers/` | Background loops outside the request cycle |

```
app/
├─ main.py              app factory — wiring only, no logic
├─ core/
│  ├─ config.py         settings from .env (import `settings`, never os.environ)
│  ├─ security.py       camera token + officer PIN        (Phase 16)
│  └─ events.py         in-process pub/sub for WebSocket  (Phase 8)
├─ api/
│  ├─ router.py         mounts every route module under /api
│  ├─ deps.py           shared dependencies               (Phase 4)
│  └─ routes/
│     ├─ health.py      GET /api/health                   ✅ built
│     ├─ cameras.py                                       (Phase 4)
│     ├─ frames.py                                        (Phase 5)
│     ├─ incidents.py                                     (Phase 9)
│     ├─ matches.py                                       (Phase 10)
│     ├─ journeys.py                                      (Phase 13)
│     └─ ws.py          WS /ws/live                       (Phase 8)
├─ services/            ingest, evidence, matching, journeys, watchlist
├─ schemas/             Pydantic models
├─ db/
│  ├─ session.py        connection handling               ✅ built
│  ├─ queries/          one module per table              (Phase 3)
│  └─ migrations/       schema.sql                        (Phase 2)
└─ workers/             frame_worker, retention
```

Empty layers are created as the phase that needs them arrives — the folder
docstrings say what belongs where.

## The dependency rule

```
routes  →  services  →  db/queries  →  Postgres
                    ↘  pipeline/*  (Teammate 1's AI functions)
```

Arrows point one way only.

- A route that writes SQL is a bug.
- A service that imports `fastapi` is a bug.
- `pipeline/` importing anything from `api/` is a bug.

Following this is what makes Teammate 1's code swappable — Phase 5 runs against a
stub `process_frame`, Phase 7 drops in the real one, and no route changes.

## Running

```powershell
cd api
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- <http://localhost:8000/api/health> — API + Postgres round-trip
- <http://localhost:8000/docs> — interactive OpenAPI docs

`--host 0.0.0.0` is required so phones on the hotspot can reach `POST /api/frames`.

## Conventions

- Python **3.12** only — `py -3.12 -m venv .venv`
- Settings come from `app.core.config.settings`, never `os.environ`
- Connections come from `app.db.session`, never a bare `psycopg.connect`
- Every new route module exposes `router = APIRouter(...)` and gets mounted in `app/api/router.py`
- Type-hint function signatures; FastAPI generates the docs from them
