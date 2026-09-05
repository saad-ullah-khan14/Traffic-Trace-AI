# Traffic-Trace-Backend

> **Two repositories.** This one holds the API, the AI pipeline and the shared
> contracts. The dashboard lives in **Traffic-Trace-Frontend** and must be cloned
> into `dashboard/` inside this folder — `scripts/download_tiles.py` writes into
> `dashboard/public/tiles`, and `api/` imports `pipeline/` as a sibling, so the
> layout matters:
>
> ```text
> Traffic_Trace/            <- Traffic-Trace-Backend (this repo)
> └── dashboard/            <- Traffic-Trace-Frontend
> ```
>
> ```powershell
> git clone https://github.com/UniDev143/Traffic-Trace-Backend.git Traffic_Trace
> cd Traffic_Trace
> git clone https://github.com/UniDev143/Traffic-Trace-Frontend.git dashboard
> ```


Traffic-violation tracking for vehicles with **no readable number plate**.

Phone cameras at fixed GPS points send sampled frames. Every vehicle at every camera is
given a visual fingerprint (ReID embeddings + attributes) and stored as a **sighting** —
always, unconditionally. A violation with an unreadable plate opens an **incident**. The
matching engine (space-time gate → similarity → score fusion) proposes candidate
sightings, an officer confirms one, and confirmed matches chain into a **journey** drawn
on a map.

> Every vehicle is fingerprinted always. Only violations open incidents.

---

## Requirements

| Tool | Version | Note |
|---|---|---|
| Python | **3.12** | invoke as `py -3.12`. The default `python` on PATH is 3.14 and **will not work** |
| Node.js | 22.x | |
| PostgreSQL | **18**, native Windows service | **not** Docker — see `PROGRESS.md` §4.2 |

No Docker anywhere. Postgres runs as the Windows service `postgresql-x64-18` and
autostarts with the machine.

---

## First-time setup

```powershell
# 1. Database (already created on this machine)
psql -U postgres -h 127.0.0.1 -c "CREATE DATABASE traffic_trace"

# 2. API
cd api
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env     # REQUIRED. Without it the API refuses to start:
                           # DATABASE_URL and OFFICER_PIN have no defaults

# 3. Dashboard
cd ..\dashboard
npm install
```

---

## Running it

Two terminals.

**Terminal 1 — API** (`http://localhost:8000`)
```powershell
cd api
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 — dashboard** (`http://localhost:3000`)
```powershell
cd dashboard
npm run build
npm run start -- -H 0.0.0.0 -p 3000
```

> ⚠️ Use the **production build** whenever a phone is involved, not `npm run dev`.
> The dev build ships ~4 MB of JavaScript versus 563 KB; over a phone hotspot it
> often never finishes hydrating, so the page renders but every button silently
> does nothing. `npm run dev` is fine for laptop-only work.

Check both are alive:
- API health incl. a real Postgres round-trip → <http://localhost:8000/api/health>
- Interactive API docs → <http://localhost:8000/docs>
- Dashboard → <http://localhost:3000>

`--host 0.0.0.0` is deliberate: phones on the laptop's hotspot must reach
`POST /api/frames`. Find the laptop's IP with `ipconfig` and browse to
`http://<laptop-ip>:3000/camera` from the phone.

---

## Layout

| Directory | Owner | Contents |
|---|---|---|
| `api/` | Muhammad | FastAPI app, ingest worker, DB layer, WebSocket bus |
| `dashboard/` | Muhammad | Next.js + Tailwind + shadcn/ui — map, incident review, journeys |
| `pipeline/` | Teammate 1 | pure AI functions, no DB or HTTP |
| `tools/` | Teammate 1 | `replay.py`, the demo fallback |
| `contracts/` | **joint** | `schema.sql`, `endpoints.md` — frozen in Phase 2 |
| `evidence/` | runtime | vehicle crops named by SHA-256, gitignored |

`api/` is the only code that touches the database or the network. It imports and calls
`pipeline/`.

---

## Project state

**`PROGRESS.md` is the source of truth** for what is built, every decision taken, and
how the stack deviates from the original roadmap. Read it before the roadmap document —
four things in that roadmap (Docker, Postgres 16, pgvector, Python 3.11) are no longer
accurate.

**`FILES.md`** lists every file and what it does, including the ones not written yet and
which phase creates them.
