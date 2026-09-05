# Traffic_Trace — Progress & Handoff Log

> 📌 **New session? Read `HANDOFF.md` first.** It is the current state in one
> page: how to run it, what is still open, and the measurements that must not be
> re-derived. This file is the full history — ~1900 lines, appended once per
> phase — and is for looking up *why* something in HANDOFF.md is the way it is.
>
> **Purpose of this file.** A running record of what has actually been built and decided, written so that an assistant with *no* prior context can pick up the project from this file alone. A new section is appended at the end of every completed phase.
>
> **Last updated:** 30 Aug 2026 · **Current state:** **Phases 0–18 and 20 complete**, Checkpoints A–D passed, **pipeline_v9 + `tools/replay.py` integrated**, and a **full pre-demo audit run end to end — 52/52 checks passing** after fixing a fatal ingest-latency bug (see the last section). All seven pipeline functions are real. **The demo has been pushed back**, and the time was spent on the product boundary (plate readable → ANPR, unreadable → this feature) and a review screen that asks one question at a time. **Now tracks motorcycles only** (the only class `no_helmet` can apply to). Remaining: **19 — two live rehearsals**. **Pushed to two GitHub repos** (see §0).

---

## 0. START HERE — read this first

**Status: all build phases (0–16) are complete and working.** What remains is demo
logistics, the pitch deck, rehearsal, and freeze — phases 17–20.

### Quick facts

| | |
|---|---|
| Repo root | `d:\Daniyal Files\Traffic_Trace` |
| Python | **3.12** — always `py -3.12`. The default `python` is 3.14 and breaks |
| Database | native **PostgreSQL 18**, service `postgresql-x64-18`, autostarts |
| DB URL | `postgresql://postgres:trafficdev@127.0.0.1:5432/traffic_trace` |
| Officer PIN | `4321` (in `api/.env`) |
| Camera tokens | `SELECT name, token FROM cameras;` |
| **No Docker, ever** | see §4.2 — the Windows image has virtualization stripped |

### Two repositories

The project is **split across two GitHub repos**, but the folders must stay laid
out exactly like this on disk — `api/` imports `pipeline/` as a sibling, and
`scripts/download_tiles.py` writes into `../dashboard/public/tiles`:

```text
Traffic_Trace/            <- Traffic-Trace-Backend   (api, pipeline, contracts, tools)
└── dashboard/            <- Traffic-Trace-Frontend  (Next.js)
```

| Repo | URL |
|---|---|
| Backend | `https://github.com/UniDev143/Traffic-Trace-Backend.git` |
| Frontend | `https://github.com/UniDev143/Traffic-Trace-Frontend.git` |

`dashboard/` is listed in the backend's `.gitignore` so the two repos never track
the same file, while the folder stays where the code expects it.

Both use the **personal** GitHub account (`UniDev143`), set per-repo rather than
globally — this machine also has a company account:

```powershell
git config user.name  "Daniyal"
git config user.email "daniyalahad084@gmail.com"
# username in the remote URL so the credential manager picks the right account
git remote add origin https://UniDev143@github.com/UniDev143/<repo>.git
```

**The two model weights are committed** (`pipeline/yolov8n.pt`,
`pipeline/helmet_model.pt`, 12 MB total) even though `*.pt` is ignored. Without
them a fresh clone cannot run, and a backup of something that does not run is
not a backup.

⚠️ `PROGRESS.md` contains the local DB password and the officer PIN. They are
localhost-only, but **keep both repos private**.

### How to run it

```powershell
# Terminal 1 — API
cd "d:\Daniyal Files\Traffic_Trace\api"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# Terminal 2 — dashboard (PRODUCTION build whenever a phone is involved)
cd "d:\Daniyal Files\Traffic_Trace\dashboard"
npm run build
npm run start -- -H 0.0.0.0 -p 3000
```

Then: `/incidents` feed · `/incidents/{id}` review · `/journeys` animated route ·
`/map` live map · `/camera` phone page · `/api/health` (shows whether the real AI
is loaded) · `/docs` API reference.

### Working rules (do not break these)

1. **Daniyal runs every git command himself.** Never run `git` or `gh` — hand him
   the commands to paste. Writing `.gitignore` is fine.
2. **Update `PROGRESS.md` and `FILES.md` at the end of every phase**, unasked.
   `PROGRESS.md` = what was decided and why. `FILES.md` = what each file is for.
3. **Layered architecture.** Routes are thin, services hold logic, **all SQL lives
   in `app/db/queries/`**. A route containing SQL is a bug.
4. **`pipeline/` belongs to Teammate 1.** Only `app/services/pipeline_client.py`
   imports it. Copy his files in; never edit his logic without telling him.
5. Explain FastAPI by mapping to Express — Daniyal is a MERN developer.
6. Reply in simple Roman Urdu when he writes in Roman Urdu.

### What is left to do

| Phase | Work | State |
|---|---|---|
| 17 | Demo infra | ✅ `start_demo.ps1`, `api/scripts/preflight.py` |
| 18 | Pitch deck + demo script | ✅ `docs/PITCH.md`, `docs/DEMO_SCRIPT.md` |
| **19** | ⚡ Two clean live rehearsals + one replay-fallback run | 🔜 **unblocked** — `tools/replay.py` delivered 29 Aug and verified against the live API. Only the rehearsals themselves remain |
| 20 | Failure runbook + freeze checklist | ✅ `docs/RUNBOOK.md` written — tag and USB backup still to be *executed* |

Everything writable has been written. What remains is physical: run it, rehearse it,
back it up.

### Documents produced

| File | What it is |
|---|---|
| `docs/PITCH.md` | 8 slides — content plus speaker script |
| `docs/DEMO_SCRIPT.md` | Minute-by-minute 7-minute run, who says what, fallback wording |
| `docs/RUNBOOK.md` | 14 failure scenarios, each a 60-second fix, plus the freeze checklist |
| `docs/STATS.md` | Measured numbers, each with the command that produced it |
| `start_demo.ps1` | Cold laptop → running system. Refuses to report READY if the pipeline is a stub |
| `api/scripts/preflight.py` | "Is this machine ready to demo?" — run it the night before |

### Immediate actions for Daniyal

1. ~~Git~~ — **done.** Both repos pushed; see "Two repositories" above.
2. **Decide the three real camera locations.** Currently placeholders around
   Karachi. Once fixed: update `scripts/seed_cameras.py` and **re-run
   `scripts/download_tiles.py` while there is still internet** — the demo has none.
3. **Walk the whole demo himself** — phone → incident → review → confirm →
   journey. He has only watched it up to Phase 6 with his own eyes.

### Still owed by Teammate 1

Nothing blocking. `tools/replay.py` and `dedupe` both landed on 29 Aug — see
§"pipeline_v9 integration" at the end of this file.

The one open item is **weight tuning on real street data** (his Phase 11). He did
a best-effort pass on a small test set; the weights in `pipeline/matcher.py` are
still hand-set. Only worth revisiting if the review screen ranks badly outdoors.

### Known risks

- **CLIP alone cannot identify a vehicle.** Measured: a *different*-vehicle pair
  scored 0.9179 while a *same*-vehicle pair scored 0.8703. His `score_candidates`
  compensates by weighting CLIP lowest (0.20); colour histogram and space-time
  carry the identification. Do not "fix" this by trusting `veh_emb` more.
- **His space-time score rises with the time gap**, so inside a 30-minute window
  nearly everything scores ~1.0 and it acts mostly as a constant plus a hard
  reject. First thing to revisit when tuning.
- **His `pipeline/__init__.py` imports `alpr` at module load**, so a missing
  `fast_alpr` breaks the *entire* pipeline, not just plate reading.
- **`npm run dev` is unusable on a phone** — ~4 MB of JS never finishes loading
  over a hotspot and the page renders without hydrating. Always the production build.

---

## 1. What this project is

A traffic-violation system for vehicles with **no readable number plate**.

Phone cameras at fixed GPS points send sampled frames. Every vehicle at every camera gets a visual "fingerprint" (ReID embeddings + attributes) stored as a **sighting** — always, unconditionally. A violation (e.g. no helmet) with an unreadable plate opens an **incident**. A matching engine (space-time gate → similarity search → score fusion) proposes top-K candidate sightings. A police officer confirms on a dashboard. Confirmed matches chain into a **journey** drawn on a map.

Key rule: *every vehicle is fingerprinted always; only violations open incidents.*

**Timeline:** build window 22–27 Aug 2026 · regional round 28–30 Aug 2026.

**Team split:**
- **Muhammad (this repo's owner)** — everything except AI: Postgres, FastAPI backend, ingest worker, WebSocket realtime, Next.js dashboard, phone camera page, demo infra, pitch deck.
- **Teammate 1** — pure Python functions in `pipeline/`: `process_frame`, `read_plate`, `score_candidates`, `is_reachable`, `check_watchlist`, `build_journey`, `dedupe`. Plus `tools/replay.py`.

Muhammad's code is the only code touching DB and HTTP; it calls Teammate 1's functions.

---

## 2. Stack as actually built

> ⚠️ Three items deviate from the original roadmap. They are marked **[CHANGED]** and explained in §4. Anyone working from the original roadmap document will be wrong on these three points.

| Layer | What we're using |
|---|---|
| Backend | FastAPI + Uvicorn, single process |
| Language | **Python 3.12.9** — **[CHANGED]** roadmap said 3.11 |
| Database | **Native PostgreSQL 18.4 Windows service** — **[CHANGED]** roadmap said Postgres 16 in Docker |
| Vector search | **`float4[]` column + numpy cosine in the worker** — **[CHANGED]** roadmap said pgvector |
| Frontend | Next.js + Tailwind + shadcn/ui |
| Maps | Leaflet + react-leaflet, cached **offline** OSM tiles |
| Realtime | Native WebSocket |
| Evidence | Local folder + SHA-256 hash |
| Demo | Fully offline, one laptop + phone hotspot |

**Repo layout (planned, not yet created):**
`api/` (Muhammad) · `pipeline/` (Teammate 1) · `dashboard/` (Muhammad) · `tools/replay.py` (Teammate 1) · `contracts/` (shared)

---

## 3. Environment — verified working

Machine: `FAHADSPC`, Windows 11 Pro 24H2 (build 26100.7171).

| Component | Version / detail | Status |
|---|---|---|
| PostgreSQL | 18.4, service `postgresql-x64-18`, Automatic start | ✅ running, port 5432 |
| Project database | `traffic_trace` | ✅ created |
| DB credentials | user `postgres` / password `trafficdev` | ✅ verified |
| psql on PATH | `C:\Program Files\PostgreSQL\18\bin` | ✅ user PATH |
| pgAdmin 4 | bundled with PG18 | ✅ installed |
| Python | 3.12.9 — invoke as **`py -3.12`** | ✅ |
| Node / npm | 22.17.0 / 10.9.2 | ✅ |
| git | 2.50.1, identity `Daniyal` | ✅ |

**Python dependency set — all installed as native `cp312` wheels, no compiler needed:**
fastapi 0.141.1 · uvicorn[standard] 0.52.3 · psycopg[binary] 3.3.4 · numpy 2.5.2 · pillow 12.3.0 · python-multipart 0.0.32 · pydantic-settings 2.15.0

**Critical round-trip verified against the live database:**
```
float4[] -> numpy: [1. 2. 3.] float32
```
Postgres hands embeddings directly to numpy as `float32`. No conversion layer needed.

Other databases on this server: `practice_db` — unrelated to this project, **do not drop it**.

---

## 4. Decisions made, and why

### 4.1 Python 3.12, not 3.11 or 3.14 **[CHANGED]**
3.11 is not installed. The machine's default `python` on PATH is **3.14.6 and must not be used** — no binary wheels exist for it, so torch/psycopg/onnxruntime fail at install with a confusing compiler error. Always `py -3.12 -m venv`.

⚡ **Teammate 1 must build `pipeline/` on 3.12** or the two `requirements.txt` files diverge.

### 4.2 Native Postgres 18, not Docker **[CHANGED]**
**Docker cannot run on this laptop and never will.** The Windows image has every virtualization payload stripped out:

- `VirtualMachinePlatform` — 26 packages registered, **0** actual payload folders
- `Microsoft-Windows-Subsystem-Linux` — 0 packages, 0 folders (removed entirely)
- `Microsoft-Hyper-V-All`, `Containers`, `HypervisorPlatform` — all fail `0x800f081f`
- `DISM /RestoreHealth` completes with exit 0 and changes nothing
- CPU virtualization *is* enabled in BIOS — hardware is not the problem
- Windows is also unactivated (`LicenseStatus: 5`)

Postgres 18 was already installed on the machine and does everything needed. **Do not retry Docker/WSL2/Hyper-V.** The only untried fix is repairing Windows from an official ISO via `DISM /Source:`, rejected as too slow before the hackathon.

Side effects: `docker-compose.yml` is not part of the run instructions; Postgres autostarts as a Windows service, which simplifies `start_demo.sh` in Phase 17.

### 4.3 No pgvector — `float4[]` + numpy cosine **[CHANGED]**
- `sightings.veh_emb` / `rider_emb` are `real[]` (= `float4[]`), not `vector(DIM)`
- SQL performs the **space-time gate only** (time window + reachable cameras)
- The worker loads gated candidates and ranks by **cosine in numpy**
- Embeddings are **L2-normalized by Teammate 1** inside `process_frame` and arrive unit-length, so cosine reduces to a plain dot product. **The API must not re-normalize.** (Agreed at Checkpoint A; this reversed our earlier assumption that the API would own normalization)
- `contracts/schema.sql` keeps pgvector in a comment as the production/scale path

**Why:** pgvector ships no prebuilt Windows binaries; building it needs ~4 GB of Visual Studio Build Tools. At demo scale (hundreds of gated candidates) brute-force numpy is microseconds — an index only pays off in the hundreds of thousands of rows.

⚡ **This changes none of Teammate 1's function signatures.** `score_candidates` still receives embeddings. But the database no longer performs similarity — the worker does.

**Phase 3's "Done when" is amended to:** *gated SQL query + numpy top-5 in under 50 ms.*

---

## 5. Amended contracts

**`contracts/schema.sql` is authoritative and has been applied to the database.** Summary:

```sql
cameras   (id, name, lat, lng, heading, token, created_at)
sightings (id, camera_id→cameras, ts, vehicle_type, bbox jsonb,
           veh_emb real[] NOT NULL,   -- CHANGED from vector(DIM); CHECK length = 512
           rider_emb real[],          -- CHANGED from vector(DIM); NULL when no rider
           attrs jsonb, confidence, crop_path, crop_hash, created_at)
incidents (id, sighting_id→sightings, violation, plate_text NULL,
           status open|confirmed|closed, created_at)
matches   (id, incident_id→incidents, sighting_id→sightings,
           score, breakdown jsonb, decision NULL|confirm|reject, decided_at,
           UNIQUE (incident_id, sighting_id))
journeys  (id, incident_id→incidents UNIQUE, sighting_ids uuid[], updated_at)
-- DIM = 512 (CLIP ViT-B/32), agreed at Checkpoint A, enforced by CHECK constraints
-- Embeddings arrive ALREADY L2-normalized from Teammate 1; API must not re-normalize
-- Production/scale path: pgvector `vector(512)` + an hnsw index
-- Retention: unlinked sightings auto-deleted after 48h (periodic job, Phase 16)
```

**Agreed constants (Checkpoint A):**

| Constant | Value |
|---|---|
| `EMBEDDING_DIM` | **512**, CLIP ViT-B/32. Single source of truth: `pipeline/types.py` |
| Normalization owner | **Teammate 1**, inside `process_frame` |
| Max speed / grace | **60 km/h** / **30 s** — identical in the SQL gate and `is_reachable` |
| Candidate handoff | API ranks visually, sends **top-20**; `score_candidates` fuses the rest |
| bbox | `[x1, y1, x2, y2]` pixels |
| Confidence / score | `0.0`–`1.0` |

**Endpoints:** `POST /api/cameras` · `POST /api/frames` · `GET /api/incidents` · `GET /api/incidents/{id}` · `POST /api/matches/{id}/decision` · `GET /api/journeys/{incident_id}` · `WS /ws/live` with events `sighting | incident | match_suggestion | journey_update`.

---

## 6. Open items

**⚡ Must tell Teammate 1 before Integration Checkpoint A (Phase 2):**
1. Python 3.12, not 3.11
2. No pgvector — DB does the gate, worker does similarity
3. No Docker in the run instructions
4. Settle the **embedding dimension** — everything downstream inherits it

**Camera registration flow — decided 18 Aug 2026, not yet built (Phases 4 and 6):**

1. `seed_cameras.py` creates the 3 cameras, each with a secret token (**done**)
2. Phone opens `/camera` and the operator types that camera's secret
3. Server validates the token — this phone is now that camera
4. Phone reads GPS and sends its position; the pin appears on the map
5. **Fallback: drag the pin manually.** Not optional — geolocation needs the same Chrome insecure-origin flag as the camera and can hang or return a bad fix between buildings. One drag control is the difference between a recoverable and a dead demo.

`heading` stays out of the UI and is set in the seed file: nothing in the matching maths uses it, it only draws a direction cone on the map.

**Prep-week inputs the roadmap assumes exist, but which do not yet:**
- [ ] Camera-page spike on a real phone (`getUserMedia` + Chrome insecure-origin flag over the hotspot) — **highest-risk unknown**; if phones won't stream, Phase 6 collapses
- [ ] Offline OSM tiles for the demo area — needs internet *now*; requires the 3 camera locations to be chosen; blocks Phases 12 and 13
- [ ] Dashboard skeleton with a live WebSocket feed
- [x] ~~pgvector queries practiced~~ — no longer applicable

**Deferred to Phase 16 (Hardening):** Postgres currently has `listen_addresses = '*'`, so it accepts connections from any network it's on. Only FastAPI needs to face the phone hotspot; the database should be localhost-only.

---

## 7. Phase log

### Phase 0 — Environment setup · ✅ complete · 17 Aug 2026

Not a roadmap phase; prerequisite work done before Phase 1.

**Done:**
- Diagnosed and ruled out Docker/WSL2/Hyper-V permanently (see §4.2)
- Ran `DISM /RestoreHealth` — succeeded but could not restore stripped features
- Discovered PostgreSQL 18.4 already installed and running; adopted it instead of installing Postgres 16
- Reset the unknown `postgres` password to `trafficdev` via a temporary `pg_hba.conf` trust flip, then restored `scram-sha-256` auth. Existing data untouched
- Created the `traffic_trace` database
- Added `psql` to the user PATH
- Verified the full Python 3.12 dependency set installs as native wheels, and confirmed the `float4[]` → numpy `float32` round-trip against the live DB
- Removed 3.4 GB of dead Docker install files; C: went 13.9 → 17.2 GB free

**Not done:** no project code written; the repo directory is still empty.

**Next:** Phase 1 — repo + infrastructure.

---

### Phase 1 — Repo + infrastructure · ✅ complete · 17 Aug 2026

**Goal:** monorepo skeleton so every later phase has somewhere to put code.

**Done-when (amended — no Docker):** Postgres service healthy · API dev server starts · dashboard dev server starts. **All three verified.**

**Structure created:**
```
Traffic_Trace/
├─ api/            app/main.py, app/__init__.py, requirements.txt, .env, .env.example, .venv/
├─ dashboard/      Next.js 16.3.1 + TypeScript + Tailwind v4 + shadcn/ui
├─ pipeline/       README.md (Teammate 1's brief)
├─ tools/          README.md (replay.py brief)
├─ contracts/      README.md (Phase 2 placeholder)
├─ evidence/       .gitkeep (crop storage, gitignored)
├─ .gitignore
├─ README.md
└─ PROGRESS.md
```

**api/ — layered architecture.** At Daniyal's request the backend is organised in separated layers rather than one file, following the Express conventions he knows. Full documentation in `api/README.md`. The dependency rule:

```text
routes → services → db/queries → Postgres
                 ↘ pipeline/*  (Teammate 1's AI functions)
```

Arrows point one way only. A route containing SQL is a bug; a service importing `fastapi` is a bug; `pipeline/` importing from `api/` is a bug. This separation is what makes Teammate 1's functions swappable — Phase 5 runs against a stub `process_frame`, Phase 7 drops in the real one, and no route changes.

| Layer | Path | Built? |
|---|---|---|
| App factory (wiring only) | `app/main.py` | ✅ |
| Settings from `.env` | `app/core/config.py` | ✅ |
| Route mounting | `app/api/router.py` | ✅ |
| Health route | `app/api/routes/health.py` | ✅ |
| Connection handling | `app/db/session.py` | ✅ |
| Business logic | `app/services/` | package + docstring only |
| Pydantic models | `app/schemas/` | package + docstring only |
| Background loops | `app/workers/` | package + docstring only |
| SQL per table | `app/db/queries/` | Phase 3 |
| Shared guards (middleware) | `app/api/deps.py` | Phase 4 |
| Event bus | `app/core/events.py` | Phase 8 |

Empty layers get created when the phase that needs them arrives; each package's `__init__.py` docstring already states what belongs there, so there are no meaningless placeholder files.

**api/ — environment.** venv on Python 3.12.9, 26 packages from `requirements.txt`, all native `cp312` wheels. `GET /api/health` opens a real Postgres connection rather than returning a canned OK:
```json
{"status":"ok","db":{"ok":true,"database":"traffic_trace","version":"PostgreSQL 18.4"}}
```
`/openapi.json` serves correctly, so `/docs` works. Verified: uvicorn responded in 2s.

**dashboard/** — `create-next-app` with `--typescript --tailwind --eslint --app --src-dir`, then `shadcn init --defaults`. 364 packages, 0 vulnerabilities. shadcn detected **Tailwind v4** and wrote `components.json`, `src/components/ui/button.tsx`, `src/lib/utils.ts`. Verified: `npm run dev` ready in 3.1s, HTTP 200, page renders.

**Versions pinned this phase:** Next.js 16.3.1 (Turbopack) · Tailwind v4 · React 19 · FastAPI 0.141.1 · uvicorn 0.52.3 · psycopg 3.3.4 · numpy 2.5.2.

**Useful for later:** the laptop's current LAN address is **`10.44.235.6`** — `next dev` reports it as the Network URL. Phones will hit `http://<laptop-ip>:3000/camera` and `http://<laptop-ip>:8000/api/frames` in Phase 6. Re-check it with `ipconfig` once the hotspot is up; it will differ.

**⚠️ Outstanding — must be handled before the first commit:** `create-next-app` auto-ran `git init`, leaving a nested repo at `dashboard/.git`. If the root repo is initialised with that in place, git tracks `dashboard/` as an opaque gitlink and none of its files are committed. Remove it first:
```powershell
Remove-Item "d:\Daniyal Files\Traffic_Trace\dashboard\.git" -Recurse -Force
```

**Not done / deliberately deferred:**
- No `docker-compose.yml` — Docker is impossible here (§4.2); Postgres autostarts as a service
- No git init/commit — Daniyal owns all version control himself
- No routers, config module, ingest, or WebSocket bus — those are Phases 4–8. `main.py` is intentionally minimal, just enough to prove the stack is wired
- `contracts/schema.sql` and `pipeline/types.py` not written — Phase 2 is joint work

**Next:** Phase 2 — ⚡ contracts freeze (JOINT with Teammate 1). Blocked on two answers from him: the **embedding dimension** (2048 fast-reid vs 512 CLIP) and his exact **`is_reachable`** rule.

---

### Phase 2 — ⚡ Contracts freeze · ✅ complete · 18 Aug 2026 · **Integration Checkpoint A**

**Goal:** agree the database schema, the API surface, and the shared constants, so neither side can drift.

**Done-when:** schema applies cleanly to Postgres · both files committed. **Schema verified applied; commit is Daniyal's to run.**

**Teammate 1 confirmed all six items:**

| Item | Agreed |
|---|---|
| Embedding dimension | **512** — CLIP ViT-B/32 |
| Normalization owner | **Teammate 1**, inside `process_frame`. API must not duplicate |
| Reachability | **60 km/h max, 30 s grace** |
| Candidate handoff | option (b) — API sends **top-20 pre-ranked**, he fuses the rest |
| Python | **3.12** on both sides |
| bbox | `[x1, y1, x2, y2]` in pixels |

He is writing `pipeline/types.py` with dataclasses `Detection`, `Fingerprint`, `Sighting`, `Violation`, `FrameResult`, `MatchCandidate`, `Journey`.

**⚠️ Decision reversed:** we had planned for the API to L2-normalize embeddings on write. Teammate 1 owns it instead. The API must **not** re-normalize — doing it twice is harmless mathematically but hides a real bug: if he ever stops normalizing, our re-normalization would mask it until scores quietly degraded. Instead the ingest worker should **assert** the norm is ≈1.0 and log loudly if not (Phase 5).

**Files written:**

- **`contracts/schema.sql`** — five tables, applied to `traffic_trace`. `real[]` (= `float4[]`) embeddings with `CHECK (array_length = 512)` at the DB boundary, so a wrong-sized vector fails loudly on INSERT rather than ranking badly in silence. Indexes: `(camera_id, ts DESC)` for the space-time gate — the hot query of Phase 11 — plus `(ts)` for retention, `(status, created_at DESC)` for the feed, `(incident_id, score DESC)` for the review UI. `ON DELETE CASCADE` throughout. Retention query included as a comment for Phase 16.
- **`contracts/endpoints.md`** — every REST endpoint with example payloads, the four WebSocket event types, the error table, and the list of `pipeline/` functions with which service calls each and in which phase.

**Verification run against the live database:**

| Test | Result |
|---|---|
| `schema.sql` applies | ✅ 5 tables, 12 indexes, exit 0 |
| 512-dim embedding insert | ✅ stored, L2 norm reads back exactly `1.000000` |
| 511-dim embedding | ✅ **rejected** by `sightings_veh_emb_dim` |
| incident → match → journey chain | ✅ all five tables populated |
| `status = 'banana'` | ✅ **rejected** by `incidents_status_valid` |
| `ON DELETE CASCADE` | ✅ deleting one camera emptied every table |

Database left clean — 0 rows everywhere.

**Deliberately left unconstrained:** `vehicle_type` and `violation` are plain `text` with no `CHECK`. Their exact label sets come from Teammate 1's model output and are not yet confirmed; a wrong guess would reject valid inserts at Checkpoint B. Add the constraints once the labels are known.

**Not done:** `pipeline/types.py` — Teammate 1 owns it and is writing it now. Not written unilaterally, since it is joint by contract.

**⚠️ Still open, highest risk:** his **exact dataclass field names**. He said he would "check from my side" but has not sent them. A field-name mismatch (`box` vs `bbox`) fails *silently* — empty results, no exception — and would surface at Checkpoint B on Day 2 with each side assuming the other is broken.

**Next:** Phase 3 — DB layer: `app/db/queries/`, the space-time gated candidate query, and seeding 3 demo cameras.

---

### Phase 3 — DB layer · ✅ complete · 18 Aug 2026

**Goal:** all SQL in one layer, the space-time gate, and the numpy ranking that replaces pgvector.

**Done-when (amended in Phase 0):** gated SQL query + numpy top-5 under 50 ms. **Achieved: 37 ms end-to-end** against 5,000 sightings.

**Built:**

| Path | Purpose |
|---|---|
| `app/core/constants.py` | The Checkpoint A values: 512 dims, 60 km/h, 30 s grace, top-20, 30-min window |
| `app/db/session.py` | Connection **pool** (was connect-per-query), `dict_row` rows |
| `app/db/numpy_types.py` | Custom psycopg loader: binary `float4[]` → `np.ndarray` |
| `app/db/queries/cameras.py` | insert, get, get-by-token, list |
| `app/db/queries/sightings.py` | insert, get, **`get_gated_candidates`**, `get_sightings_by_ids`, count |
| `app/db/queries/incidents.py` | insert, get (joined to sighting+camera), list with match counts, set status |
| `app/db/queries/matches.py` | `save_matches` (upsert), get for incident, `decide_match`, confirmed sightings |
| `app/db/queries/journeys.py` | `save_journey` (upsert), `get_journey` with ordered hops |
| `app/services/geo.py` | haversine, `min_travel_seconds`, `is_reachable`, `build_gate` |
| `app/services/matching.py` | `rank_by_cosine`, `find_candidates`, `assert_normalized` |
| `scripts/seed_cameras.py` | 3 demo cameras, idempotent |
| `scripts/bench_matching.py` | The acceptance test |
| `scripts/test_numpy_loader.py` | Byte-exactness test for the binary loader |

**Cameras seeded (⚠️ PLACEHOLDER coordinates — replace before real-world testing):**

| From → To | Distance | Minimum gap the gate enforces |
|---|---|---|
| Kalma Chowk → Model Town Link Rd | 1.87 km | 82.1 s |
| Kalma Chowk → Ichhra, Ferozepur Rd | 2.60 km | 126.0 s |
| Model Town Link Rd → Ichhra | 4.01 km | 210.3 s |

#### Performance: 118 ms → 37 ms

The first honest measurement **failed** at 118 ms. Profiling found the cause was not the query:

- Postgres executed the gate in **8 ms** (`idx_sightings_camera_ts`, top-N heapsort — the index works)
- **~90 ms** was psycopg turning 500 × 512 values into Python `float` objects
- ~11 ms was numpy building a matrix from lists-of-lists

Three fixes, each measured:

1. **Connection pool** — connect-per-query costs ~15 ms on Windows.
2. **Binary wire format + a custom numpy loader.** Reading the raw buffer as a structured dtype in one pass. Ranking went **11.5 ms → 0.9 ms** (12×).
3. **Rank on minimal columns, hydrate afterwards.** The gate now selects only `id, camera_id, ts, veh_emb`; `bbox`/`attrs` JSON is parsed for the ~20 survivors instead of all 500. Worth **~10 ms**.

**Rejected after measuring:** computing the dot product in SQL. It avoids transferring embeddings entirely, but Postgres's per-row `unnest` made it **490 ms — 10× worse**. Measured rather than assumed.

| Stage | Median | Max |
|---|---|---|
| SQL space-time gate | 38.7 ms | 42.6 ms |
| numpy cosine top-5 | 0.9 ms | 1.6 ms |
| **`find_candidates` end-to-end** | **37.2 ms** | **39.1 ms** |

#### Two bugs found and fixed

- **`ValueError: truth value of an array is ambiguous`** — `if c.get("veh_emb")` broke once embeddings became numpy arrays. Now an explicit `is not None` check.
- **`/api/health` returned column *names* instead of values.** Switching the pool to `dict_row` silently broke `version, database = cur.fetchone()`, since unpacking a dict yields its keys. Caught by re-running the Phase 1 verification — a reminder that earlier checks stay useful.

#### Design notes

- **The gate includes the origin camera** with a zero minimum gap. A vehicle that circles back and reappears at the same camera is a legitimate match; excluding it would lose that.
- **Haversine is straight-line distance**, so the gate is deliberately permissive — real roads are longer, so real travel takes at least this long. The gate must never exclude a true match, only the physically impossible.
- **`assert_normalized` warns, it does not fix.** Teammate 1 owns normalization. Silently re-normalizing would mask it if his side ever stopped, and match quality would degrade with no error anywhere.
- **`save_matches` upserts but never overwrites a decision** — re-running matching cannot erase an officer's confirm/reject.

**Not done:** no HTTP endpoints use any of this yet (Phase 4+). `pipeline.score_candidates` is not called yet — `find_candidates` produces exactly the top-20 pre-ranked list it will receive.

**Next:** Phase 4 — FastAPI skeleton: routers, config, `/evidence` static serving, and `POST /api/cameras`.

---

### Phase 4 — FastAPI skeleton · ✅ complete · 18 Aug 2026

**Done-when:** OpenAPI docs shows all endpoints · a camera registers and persists. **Both verified.**

**Built:**

| Path | Purpose |
|---|---|
| `app/schemas/cameras.py` | Pydantic models — validation and `/docs` generated from them |
| `app/api/deps.py` | `require_camera` — the `X-Camera-Token` guard (Express middleware equivalent) |
| `app/api/routes/cameras.py` | register, claim, location update, list |
| `app/db/queries/cameras.py` | added `update_camera_location` |
| `app/main.py` | mounted `/evidence` static serving |

**Endpoints now live:**

| Endpoint | Purpose |
|---|---|
| `POST /api/cameras` | Register a camera, returns its token **once** |
| `POST /api/cameras/claim` | Phone types the secret → identifies itself |
| `PATCH /api/cameras/me/location` | GPS fix or dragged pin. Token header required |
| `GET /api/cameras` | List for the map and camera picker. **Never returns tokens** |
| `GET /evidence/{file}` | Crop images straight off disk |

**Verified:** correct secret claims successfully and the response contains no token · wrong secret → 401 · location update without the header → 401 · with header → camera moves · `lat=999` → 422 from Pydantic · `/evidence` mount returns 404 for a missing file (so the mount is live) · all 4 paths in OpenAPI.

**Design notes:**

- **Location is identified by header, not by id in the path** (`/me/location`). A phone can only ever move itself; there is no request shape that lets one camera reposition another.
- **Claim returns the same 401 as the header guard.** A wrong secret is indistinguishable from a disabled camera, so the endpoint cannot be used to probe which tokens exist.
- **Tokens are write-once.** Registration is the only response that ever contains one; `GET /api/cameras` omits it. A lost token means re-seeding, which is the correct trade.
- **Camera position is not cosmetic** — it feeds the reachability gate, so a bad GPS fix changes which sightings count as reachable. Hence the mandatory manual-drag fallback in Phase 6.

**Not done:** `POST /api/frames` (Phase 5), and the phone `/camera` page (Phase 6). No pipeline call yet.

**Next:** Phase 5 — ingest endpoint + worker, with a stubbed `process_frame`.

---

### Phase 5 — Ingest endpoint + worker · ✅ complete · 18 Aug 2026

**Done-when:** posting a JPEG creates a sighting row + a crop file on disk. **Verified.**

**Built:**

| Path | Purpose |
|---|---|
| `app/services/pipeline_client.py` | **The only boundary to Teammate 1's code.** Stub fallback + field-name tolerance |
| `app/services/evidence.py` | Crops saved to disk, named by SHA-256 of their contents |
| `app/services/ingest.py` | frame → detections → sightings → incidents |
| `app/workers/frame_worker.py` | Bounded asyncio queue + consumer task |
| `app/api/routes/frames.py` | `POST /api/frames`, `GET /api/frames/stats` |
| `app/schemas/frames.py` | Response models |

**Verified:** no token → 401 · 6 frames → `202 accepted` · `processed=6 dropped=0 failed=0` · 10 sightings all with `dim=512` · 4 incidents with `plate=UNREADABLE` · crop filename re-hashes to exactly its own contents · `GET /evidence/<sha>.jpg` → 200.

Test data was left in the database (10 sightings, 4 incidents, 6 crops) — Phases 8–11 need something to display.

#### Design decisions

- **`pipeline_client.py` is the one place that imports `pipeline/`.** Phase 7 changes this file and nothing else. It also carries an alias map (`bbox`/`box`/`xyxy`, `veh_emb`/`embedding`/`feat`, …) and, when a required field is missing, logs *which fields were actually present*. This is the direct countermeasure to the silent-failure risk flagged at Checkpoint A: a name mismatch now produces a loud error naming the fix, instead of empty results.
- **The queue is bounded and drops the OLDEST frame when full.** If inference falls behind, memory stays flat and the demo degrades gracefully instead of dying. Drops are counted and surfaced at `/api/frames/stats`. (This line originally said *newest*, which is backwards — the code has always evicted the oldest, deliberately. The bound was 64 at the time; it is **8** since the 29 Aug audit, for the latency reason recorded there.)
- **One bad frame can never kill the worker.** The consumer catches everything except cancellation; otherwise ingest would stop silently while the API still looked healthy.
- **DB and PIL work runs in `asyncio.to_thread`.** Both are blocking; running them on the event loop would stall frame acceptance.
- **Capture time, not arrival time.** `ts` comes from the phone. Using arrival time would fold network delay into apparent travel time, and a phone retrying after a dropped connection would look like it teleported — corrupting the reachability gate.
- **Camera identity comes from the token header, never a form field.** A phone cannot submit frames as another camera.
- **Content-addressed crops dedupe for free.** The run produced 10 sightings but only 6 files: three sightings shared one hash because their crops were byte-identical.
- **`assert_normalized` runs on every detection**, so a regression on Teammate 1's side shows up as a warning rather than as quietly worse match scores.

**Not done:** WebSocket events (Phase 8) — the worker stores data but nothing is pushed to the dashboard yet. No matching is triggered on incident creation (Phase 11). Real AI still pending (Phase 7).

**Next:** Phase 6 — the phone `/camera` page.

---

### Phase 6 — Camera page · ✅ complete, verified on a real phone · 18 Aug 2026

**Done-when:** a real phone streams into the ingest endpoint without dying. **MET.**

**Live test result — a real Android phone, acting as the hotspot, laptop as its client:**

| Measure | Result |
|---|---|
| Frames accepted from the phone | **74** (`POST /api/frames` → 202) |
| Worker | `processed=74  dropped=0  failed=0` |
| Sightings created | 131 |
| Incidents opened | 29 |
| Crop files on disk | 126 |
| CORS preflight from the phone | `OPTIONS /api/frames` → 200 |
| GPS position update | `PATCH /api/cameras/me/location` → 200 |

The full chain works end to end: **phone → API → queue → worker → Postgres → crop on disk.** Zero drops, zero failures.

GPS moved "Kalma Chowk" from its Lahore placeholder (31.5010, 74.3260) to the real fix (25.0110, 67.0403 — Karachi), which is proof the location path genuinely works. It also means the three cameras are now ~1000 km apart, so nothing is reachable from anything; harmless for now, resolved when the real three locations are set.

**Built:**

| Path | Purpose |
|---|---|
| `src/lib/config.ts` | Derives the API URL from the browser's own hostname |
| `src/lib/api.ts` | The only place the dashboard calls the backend |
| `src/lib/motion.ts` | Greyscale-thumbnail motion detection |
| `src/hooks/useWakeLock.ts` | Keeps the phone screen awake, re-acquires after backgrounding |
| `src/app/camera/page.tsx` | The three-step page: claim → locate → stream |

**Scope call: the visual map pin was deferred to Phase 12**, where the offline tiles are set up. Phase 6 captures GPS numerically with an accuracy readout and editable lat/lng, so the risky capture loop could be built and tested without also standing up Leaflet. The manual fields *are* the mandated fallback.

#### Design decisions

- **API URL is derived at runtime from `window.location.hostname`, not baked in at build time.** The phone reaches the laptop at a hotspot address nobody knows in advance; a compiled-in `localhost` would work on the laptop and fail on every phone.
- **Self-rescheduling `setTimeout` loop, not `setInterval`.** The interval changes with motion, and `setInterval` would stack callbacks whenever an upload ran longer than the gap — on a weak hotspot that compounds into a request pile-up.
- **Motion detection on a 32×24 greyscale thumbnail.** Full-resolution differencing costs more than the capture itself on a mid-range phone. Rec. 601 luma is used because phone cameras shift white balance constantly, which would trigger false motion on a colour comparison.
- **Burst has a 3-second hold**, so a vehicle crossing the frame does not flip the rate on and off between captures.
- **Frames are skipped while an upload is in flight** rather than queued locally — piling requests onto a struggling link makes it worse.
- **Retry with exponential backoff, except on 401.** A rejected token will never succeed, so retrying it just burns the link.
- **Wake lock is re-acquired on `visibilitychange`.** Android silently drops it when the tab is backgrounded and never restores it — this is the most likely way a live demo dies without anyone noticing until the feed goes quiet.
- **Token is persisted in `localStorage`**, so a refresh or an accidental back-swipe does not mean re-typing a secret at the roadside.
- **Capture is downscaled to 960 px wide before upload.** The model gains nothing from 4K, and a hotspot loses a lot.

#### What Daniyal must test on a real phone

Laptop IP at time of writing: **`10.249.50.6`** (Wi-Fi). Re-check with `ipconfig` once the hotspot is running — it will differ.

Camera secrets:

| Camera | Token |
|---|---|
| Kalma Chowk | `YBYkUsIH0QwGmG1_mdyXI-QmoD6Lu1iU` |
| Model Town Link Rd | `mj-C8aLb1BMqvQOVWFJ8iIwmXIRxaaRr` |
| Ichhra, Ferozepur Rd | `nziUWDViA2TTCviyaCMapOnQQkhpVukC` |

The Chrome flag `unsafely-treat-insecure-origin-as-secure` must contain the **exact** origin including port, e.g. `http://10.249.50.6:3000`. It gates both `getUserMedia` and `geolocation`, so without it the camera and the GPS both fail.

#### Three things the live test exposed, all fixed

**1. `next dev` is unusable on a phone over a hotspot.** The dev build ships ~4 MB of JavaScript (React devtools, HMR client, unminified chunks). It never finished loading, so the page rendered perfectly but **never hydrated** — every button silently did nothing, the form fell back to a plain browser submit, and the field cleared itself on reload. It reads exactly like a broken app.
*Fix:* run the production build. **563 KB instead of ~4 MB.** This is also what should run on demo day: `npm run build` then `npm run start -- -H 0.0.0.0 -p 3000`.

**2. Nothing on the page said whether JavaScript had run.** Diagnosing the above took several rounds of guessing.
*Fix:* a permanent hydration indicator under the title — green "JS ready" or a red warning. On demo day it answers "is the page actually alive?" instantly.

**3. Chrome on Android does not always fire React's `onChange` for a pasted value.** The secret was visibly in the field while React's state stayed empty, so the button remained disabled — looking like a dead button next to a filled box.
*Fix:* read the value from the input ref as well as from state, listen to `onInput` too, and never disable the button — validate on submit and say what is wrong instead.

**Not done:** WebSocket status (Phase 8), the visual map (Phase 12), officer PIN (Phase 16).

**Next:** Phase 7 — ⚡ wire the real pipeline (Integration Checkpoint B), which is blocked on Teammate 1. Phases 8–10 are not blocked on him.

---

### Phase 7 — ⚡ Real pipeline wired · ✅ complete · 18 Aug 2026 · **Integration Checkpoint B**

**Done-when:** recorded street frames produce real sightings with embeddings in Postgres. **MET.**

Teammate 1 delivered his work through his Phase 6. He built against the `selftest.py` we sent — his `orchestrator.py` says *"Contract confirmed against Muhammad's selftest.py"* — and `process_frame` returned exactly the expected shape, so there were **no field-name mismatches at all**. Sending that starter kit paid for itself.

**What he delivered:** YOLOv8n detection (`detector.py`), a custom-trained helmet model (`helmet.py` + `helmet_model.pt`), CLIP ViT-B/32 fingerprints (`fingerprint.py`), and `orchestrator.py` tying them together. Placeholders remain for `read_plate`, `score_candidates`, `check_watchlist`, `build_journey`, `dedupe` — his later phases.

**Checkpoint B result — 3 real street photos:**

| Measure | Result |
|---|---|
| Sightings created | **17**, `stub=false` on every one |
| Embeddings | 512 dims, L2 norm `1.000000` |
| Attributes | real `color` + `color_histogram` |
| Violations | **2 real `no_helmet`**, both on motorcycles |
| Labels emitted | `car`, `motorcycle`, `bus`, `truck` / `no_helmet` |
| Throughput | 3 frames in ~5 s on CPU |
| Worker | `processed=3 dropped=0 failed=0` |

**Integration changes made (3):**

1. **`pipeline/detector.py`** — `YOLO("yolov8n.pt")` loaded relative to the working directory, and the API runs from `api/`, so the import crashed. Now resolved relative to the file, matching the pattern `helmet.py` already used.
2. **`pipeline_client.py`** — added the repo root to `sys.path`. `pipeline/` is a sibling of `api/`, so `import pipeline` could not resolve from uvicorn's working directory. Doing it here keeps the run command a single line instead of requiring `PYTHONPATH` everywhere.
3. **`pipeline/requirements.txt`** — written from his venv's installed versions; he had no requirements file. CPU torch builds on purpose.

**Two bugs found and fixed:**

- **QuickGELU mismatch.** `open_clip.create_model_and_transforms("ViT-B-32", pretrained="openai")` builds the model with `nn.GELU`, but the OpenAI weights were trained with QuickGELU. open_clip warned; the result is degraded embeddings, which means degraded match scores — the one thing the whole system rests on. Fixed to `"ViT-B-32-quickgelu"`.
- **`read_plate` signature mismatch.** Ours called `read_plate(image_bytes, bbox)`; his is `read_plate(vehicle_crop)`. It "worked" only because the exception was caught and `None` is the correct answer today — so once his Phase 8 lands it would have silently never run. Our side now crops (with cv2, since the rest of `pipeline/` is BGR) and calls his signature.

#### ⚠️ Risk found: CLIP alone cannot tell two motorcycles apart

Measured on his own paired test images — two photos each of bike A and bike B:

| Pair | Cosine |
|---|---|
| a1 ↔ a2 (**same** bike) | **0.9332** |
| a1 ↔ b1 (*different* bikes) | **0.9179** |
| b1 ↔ b2 (**same** bike) | 0.8703 |
| a1 ↔ b2 (different) | 0.8391 |

A *different*-vehicle pair (0.9179) scores higher than a *same*-vehicle pair (0.8703), and everything sits in a narrow 0.84–0.93 band. This confirms the warning in his `fingerprint.py`: CLIP captures scene semantics, not vehicle identity.

**Consequences:** ranking by `veh_emb` cosine alone gives a noisy top-20. It is a usable pre-filter — the true match generally lands inside the top 20 — but the *ordering* is close to arbitrary, so the officer's first candidate will often be wrong.

**Mitigations, in order of cost:**

1. `score_candidates` (his Phase 9) must lean on `color_histogram` and space-time, **not** on `veh_emb`. He already designed for this; it needs saying explicitly.
2. Mean-centering the embeddings before comparison — CLIP vectors occupy a narrow cone, and subtracting the dataset mean sharply increases spread. Roughly a two-line change on our ranking side, worth trying if Phase 11 candidates look random.
3. A real ReID model instead of CLIP. Correct, and almost certainly out of time.

**Not done:** matching endpoints (Phase 11) — `score_candidates` is still his placeholder returning `[]`.

**Skipped deliberately:** a `CHECK` constraint pinning `vehicle_type` to his four labels. It is a display-only field, so a wrong label costs nothing, while a rejected INSERT loses a frame mid-demo. Add it only if label drift actually causes a problem.

---

### Code audit — 12 issues found, all fixed · 18 Aug 2026

A full review of `api/`, `dashboard/src/` and `contracts/` after Phase 6. Four findings were serious enough to have broken the demo.

#### High

**1. CORS blocked every request from a phone.** `CORS_ORIGINS` allowed only `http://localhost:3000`, but phones load the dashboard at `http://<laptop-ip>:3000`. Preflight would have failed on claim, GPS and every frame — **Phase 6's phone test could never have passed.**
*Fix:* `CORS_ORIGIN_REGEX` matching localhost plus the private ranges a hotspot hands out, on any port. The origin cannot be known before the hotspot assigns it, so an explicit list was the wrong shape. Not a bare wildcard — nothing routable from the internet is accepted.

**2. A page reload silently moved the camera to (0, 0).** The `localStorage` restore path set the phase but never populated the lat/lng fields, and `Number("")` is `0`, which passes `Number.isFinite`. Saving would have parked the camera in the Atlantic; the reachability gate would then return zero candidates for every incident, forever, with no error anywhere.
*Fix:* seed the fields from the restored camera, and reject blank, out-of-range and exactly-(0,0) input explicitly.

**3. A broken real pipeline fell back to the stub in silence.** `except Exception:` around the import, with no logging. At Checkpoint B this would have produced green counters and plausible incidents built entirely from random numbers — the single worst failure mode available.
*Fix:* `ModuleNotFoundError` (expected pre-Phase 7) warns; any other import error logs at ERROR with a traceback and the words "every sighting from now on is FAKE". `/api/health` now reports `pipeline.real` and a status string, so the question is answerable in one request.

**4. The gate discarded the sightings the product exists to find.** `ORDER BY s.ts DESC LIMIT 500` over a symmetric ±30-minute window keeps only the newest rows — so past 500 candidates it threw away everything *before* the incident, which is precisely the earlier appearance the whole system is built to recover.
*Fix:* two index-ordered scans, one each side of the incident, half the budget each, `UNION ALL`. Ordering by `abs(ts - t0)` would also have been correct but sorts on a computed expression no index can serve; splitting keeps both halves on `idx_sightings_camera_ts` and guarantees the past is represented.

#### Medium

**5. Empty embeddings passed the dimension CHECK.** `array_length('{}'::real[], 1)` is NULL, and a CHECK evaluating to NULL *passes*. An empty vector was accepted, producing a permanently unmatchable sighting.
*Fix:* `coalesce(array_length(...), 0)`. Applied as `contracts/migrations/001_fix_empty_embedding_check.sql`, since the schema was already live. Verified rejecting.

**6. The frozen contract disagreed with the code.** `endpoints.md` documented `camera_id`/`token` as form fields for `POST /api/frames`; the code requires the `X-Camera-Token` header. **`tools/replay.py` written to the contract would have 401'd on every frame** — and replay is the demo's fallback path.
*Fix:* corrected the contract, with a curl example and a note flagging the change for Teammate 1.

**7. The queue evicted the wrong end.** The docstring promised the oldest frame was dropped; `put_nowait` drops the newest. During a motion burst the queue would hold stale empty-street frames and discard the ones containing the violation.
*Fix:* evict the oldest to make room, matching the documented and correct intent.

#### Low

**8.** Retries fired on 400/413, stalling the capture loop ~2 s for a request that could never succeed → only 5xx and network errors retry now.
**9.** `useWakeLock` leaked its sentinel on re-acquire, and the stale `release` listener flipped the status tile to "off" while a lock was held.
**10.** `POST /api/frames` read the whole body before checking the size limit → declared size is checked first, then re-checked after reading, since the declared value can be absent or a lie.
**11.** `read_plate` ran once per violation instead of once per detection — two violations on one vehicle meant two OCR passes that could disagree.
**12.** Benchmark anchored the incident at `now()`, leaving the forward scan empty and understating the gate's real work → now anchored mid-window.

#### Verification after the fixes

| Check | Result |
|---|---|
| CORS from `10.249.50.6:3000`, `192.168.1.55:3000`, `localhost:3000` | ✅ allowed |
| CORS from `evil.example.com` | ✅ blocked |
| `/api/health` reports pipeline mode | ✅ `{"real": false, "status": "stub (pipeline module not present)"}` |
| Empty embedding insert | ✅ rejected by the migrated constraint |
| numpy loader byte-exactness | ✅ all pass |
| Camera endpoints (401/422/claim/move) | ✅ all pass |
| Ingest: 6 frames → sightings, incidents, crops, SHA-256 | ✅ all pass |
| Dashboard typecheck | ✅ clean |
| **Matching latency** | ✅ **43.4 ms** (was 37 ms, correctness cost ~6 ms) |

The latency figure is honest: fixing finding 4 made the gate do strictly more work, and the earlier 33 ms reading was an artifact of one-sided test data. 43 ms at 5,000 sightings still leaves ~7 ms of headroom, and real demo volumes are far smaller.

---

*Note: `trafficdev` is a localhost-only development password with no value outside this laptop. It is recorded here because it is needed context, and belongs in `api/.env` (gitignored) once Phase 1 creates it.*

### Phase 8 — WebSocket live bus · ✅ complete · 18 Aug 2026

**Done-when:** browser logs events live while frames arrive. **Verified end to end** — a posted frame produced `sighting` and `incident` events on a connected client, each carrying its crop URL.

| Path | Purpose |
|---|---|
| `app/core/events.py` | The bus: a set of sockets and a broadcast function |
| `app/api/routes/ws.py` | `WS /ws/live` |
| `dashboard/src/lib/ws.ts` | Client with auto-reconnect and backoff |
| `dashboard/src/app/page.tsx` | Live monitor (replaced the Next.js default) |

**Decisions:**

- **No broker, no Redis, no pub/sub library.** The API is one uvicorn process by design, so there is nothing to coordinate across. A set of sockets and `asyncio.gather` is the whole implementation.
- **Events are fire-and-forget.** A client that misses one is not re-sent it: the dashboard reads durable state over REST and uses events only to know *when* to refresh. A dropped event costs a late update, not lost data.
- **Ingest returns events, the worker publishes them.** `ingest_frame` stays synchronous with no loop dependency, so it can run in a thread and be tested without asyncio.
- **Broadcast happens after the threaded DB work,** on the event loop — rows are already committed by then, so a client can never see an event for a row it cannot yet fetch.
- **Failed sends unsubscribe immediately.** A half-closed socket would otherwise raise on every future event.
- **`/ws/live` is mounted on the app, not `api_router`** — the contract puts it outside the `/api` prefix.
- **Crop URLs are absolute in the dashboard.** Crops are served by the API on :8000; a relative path would resolve against :3000 and 404.

**Next:** Phase 9 — dashboard shell + incident feed.

### Phases 9 & 10 — Incident feed + review UI · ✅ complete · 18 Aug 2026

**Done-when (9):** a violation appears in the feed, styled. **Done-when (10):** candidates can be reviewed and decided, and decisions persist. **Both verified.**

| Path | Purpose |
|---|---|
| `app/schemas/incidents.py` | Feed and review response models |
| `app/api/routes/incidents.py` | `GET /api/incidents`, `GET /api/incidents/{id}` |
| `app/api/routes/matches.py` | `POST /api/matches/{id}/decision` |
| `dashboard/src/components/Shell.tsx` | Sidebar + live-connection dot |
| `dashboard/src/components/PlateBadge.tsx` | The "UNREADABLE · fingerprint mode" badge |
| `dashboard/src/app/incidents/page.tsx` | The feed |
| `dashboard/src/app/incidents/[id]/page.tsx` | The review screen |
| `api/scripts/seed_matches.py` | Test-only: fills candidates until Phase 11 |

**Verified:** feed lists incidents with crops and match counts · detail returns the sighting plus 17 ranked candidates · confirm persists and flips the incident to `confirmed` · `decision: "maybe"` → 400 · unknown match → 404.

**Decisions:**

- **New incidents render straight from the WebSocket event**, then a background refetch fills in what the event omits. Waiting for a refetch before showing the card is a visible stutter on a hotspot, and that stutter happens in front of judges.
- **One request for the review screen.** The officer opens it while standing over a decision; three round-trips would be felt.
- **Keyboard shortcuts** (`c` confirm, `r` reject, arrows to move). Reviewing twenty candidates by mouse is slow, and slow is what gets seen.
- **`breakdown` keys are not fixed** — the UI renders whatever bars `score_candidates` returns. Until it lands, one honest `vehicle` bar is shown rather than four invented ones.
- **`useParams()` instead of the `params` prop** — in Next 16 that prop is a Promise, and this screen is a client component regardless.
- **Confirming sets the incident to `confirmed`.** Phase 13 hangs journey building off the same moment.

**Skipped:** extra shadcn components — plain Tailwind covers this UI, and every added component is another thing to style and keep consistent. Add when a real widget (dialog, toast) is actually needed in Phase 14.

**Observed:** the top candidate currently scores `1.0000` — it is the same vehicle from a second frame of the same photo, so the embeddings are identical. Correct behaviour, but `dedupe` (Teammate 1's Phase 14) is what stops duplicates crowding out genuinely different sightings.

**Next:** Phase 11 — matching endpoints. **Blocked on `score_candidates`.**

### Phases 12, 15, 16 · ✅ complete · 23 Aug 2026

Done out of order: 11, 13 and 14 all wait on Teammate 1, and the offline tiles needed internet, which the demo will not have.

#### Phase 12 — Live map

**Done-when:** the map is fully usable with WiFi off. **528 tiles cached, 3.5 MB, 0 failures.**

| Path | Purpose |
|---|---|
| `api/scripts/download_tiles.py` | Caches OSM tiles into `dashboard/public/tiles/` |
| `dashboard/src/components/LiveMap.tsx` | Leaflet map, camera + incident markers |
| `dashboard/src/app/map/page.tsx` | Loads it with `ssr:false` |

- **Cameras re-seeded into one city.** Two were in Lahore and one in Karachi (the GPS fix from the Phase 6 phone test), so nothing was reachable from anything. Now three points 1.4–2.1 km apart around the real fix, giving 52–96 s minimum travel times. Still placeholders — swap for the real junctions before going outdoors.
- **Markers are `divIcon`s, not image pins.** Avoids the bundler icon-path problem entirely, and camera state (live / silent / pulsing) becomes plain CSS.
- **A 5-second timer re-renders the map** so a camera fades to silent on its own — nothing arrives to trigger a render when a camera goes *quiet*.
- **Leaflet is `ssr:false`** — it touches `window` at import and would break the server render.
- Tile volume is kept small on purpose; OSM's usage policy asks that bulk downloading be avoided.

#### Phase 15 — Case file export

**Done-when:** one click produces a court-style PDF. `dashboard/src/app/incidents/[id]/report/page.tsx`, linked from the review screen.

- **No PDF library.** The browser's print-to-PDF needs no dependency, no font bundling and works offline. Tailwind `print:` utilities handle screen-versus-paper.
- Every image prints its **SHA-256** beside it, and the file's name *is* that hash — so anyone can re-hash the stored file and prove it was not altered.
- Section 5 states the limits plainly: candidates are proposed by software, **every match was confirmed by a human**, no facial recognition, 48-hour retention. Being straight about this is stronger than implying the system is autonomous.

#### Phase 16 — Hardening

**Done-when:** kill the API mid-run and everything reconnects; reset gives a clean slate. **Verified.**

| Path | Purpose |
|---|---|
| `app/core/security.py` | The `X-Officer-Pin` guard |
| `app/api/routes/admin.py` | `POST /api/admin/verify-pin`, `POST /api/admin/reset` |
| `app/workers/retention.py` | Hourly 48-hour sweep |
| `dashboard/src/components/OfficerGate.tsx` | PIN keypad + reset button |

**Verified:** verify-pin 401/401/200 for missing/wrong/right · **decision endpoint 401/401/200** · reset 401 without a PIN · reset deleted 1 sighting + 143 crops and **kept all 3 cameras** · retention sweep runs clean.

- **The PIN guards only what changes state** — match decisions and reset. The feed and map stay open so they can be projected without typing a PIN first.
- **`hmac.compare_digest`, not `==`** — a wrong PIN cannot be found one character at a time by timing the response.
- **PIN lives in `sessionStorage`**, so closing the browser re-locks it.
- **Reset keeps cameras.** Their tokens are already typed into three phones; re-registering mid-demo would cost minutes. One `DELETE FROM sightings` is enough — everything else cascades.
- **Retention deletes a crop only when no surviving row references it.** Crops are content-addressed, so two sightings can legitimately share one file.
- A failed sweep is logged and swallowed; it must never take the API down.

**Skipped:** a toast library. Errors render inline where the action was taken, which needs no dependency and no portal. Add one if Phase 14's alerts need to interrupt across pages.

**Remaining: 11, 13, 14 — all blocked on Teammate 1** (`score_candidates`, `build_journey`, `check_watchlist`). Phases 17–20 are demo logistics, deck and rehearsal.

### Phase 11 — ⚡ Matching endpoints · ✅ complete · 23 Aug 2026 · **Integration Checkpoint C**

**Done-when:** a replayed violation produces real ranked candidates in the review UI. **MET** — matching now runs automatically the moment an incident opens.

Teammate 1 delivered `score_candidates` in `pipeline/matcher.py`, and he had **kept both of our fixes** to his files (the QuickGELU model name and the YOLO path), so the copy was clean.

**His weighting, and why it is right:**

| Signal | Weight |
|---|---|
| space-time | 0.35 |
| colour histogram | 0.30 |
| vehicle embedding (CLIP) | **0.20** |
| rider embedding | 0.15 |

He deliberately gave CLIP the *lowest* weight, in direct response to the measurement in Phase 7 where a different-vehicle pair out-scored a same-vehicle pair. Missing signals (no rider on one side) have their weight redistributed rather than scoring zero, so an absent signal does not drag the total down.

**What we built:**

| Path | Purpose |
|---|---|
| `app/services/matching.py` | `build_scoring_payload` + `run_matching` |
| `app/services/pipeline_client.py` | `score_candidates` wrapper |
| `app/services/ingest.py` | Runs matching when an incident opens |

**Verified:** 6 frames across 3 cameras 150 s apart → 27 sightings, 3 incidents, **45 matches**, every one carrying a real four-signal breakdown.

**Decisions:**

- **`distance_m` and `time_gap_seconds` are computed on our side**, so his function stays pure scoring with no geography — and there is no second haversine to drift out of sync with the SQL gate.
- **Matching runs at ingest, not when the officer opens the incident.** Candidates are waiting by the time anyone clicks, instead of a spinner in front of judges.
- **The camera list is fetched lazily**, only once a violation actually opens an incident — most frames never do.
- **If `score_candidates` returns nothing or raises, we fall back to our own visual ranking.** A degraded review screen beats a blank one.
- **Embeddings are converted from numpy to lists at the boundary**, since his code and JSON both expect plain lists.

**Watch during tuning:** his space-time score rises as the time gap grows (a bigger gap means a lower required speed, hence "more plausible"). Inside a 30-minute window almost everything scores near 1.0, so at weight 0.35 it acts mostly as a constant offset plus a hard reject for the impossible — real discrimination comes from the colour histogram. That is defensible, but it is the first thing to revisit when he grid-searches the weights on real street pairs.

**Also note:** the current top scores are 1.0 on vehicle, rider and attributes because the test posts the *same image* to different cameras, so the embeddings are literally identical. Real footage will not look like this.

**Remaining: 13 and 14** — `build_journey` and `check_watchlist`, both still placeholders on his side.

### Phases 13 & 14 — Journeys + watchlist alerts · ✅ complete · 23 Aug 2026 · **Checkpoint D**

Teammate 1 delivered `build_journey`, `check_watchlist`, and — unprompted — `read_plate` (his Phase 8). All seven pipeline functions are now real except `dedupe`.

**New dependencies his ALPR pulled in:** `fast_alpr` and `onnxruntime`. Worth knowing: `__init__.py` imports `alpr` at module load, so a missing library breaks **the entire pipeline**, not just plate reading. Both are installed and in `pipeline/requirements.txt`.

#### Phase 13 — Journey view

| Path | Purpose |
|---|---|
| `app/services/journeys.py` | Assembles stops, calls his `build_journey` |
| `app/api/routes/journeys.py` | `GET /api/journeys/{incident_id}` |
| `dashboard/src/components/JourneyMap.tsx` | The animated route |
| `dashboard/src/app/journeys/page.tsx` | Incident picker + map |

**Verified:** 404 before any confirm → two confirms → a 3-stop route:

```
1. Camera 1 — Shahrah-e-Faisal  (the violation)
2. Camera 2 — Tipu Sultan Rd    conf 0.84  1.37 km  180 s
3. Camera 3 — Karsaz            conf 0.91  2.10 km  181 s
   total 3.47 km over 361 s
```

- **The violation is always stop 1**, with confidence 1.0. The journey starts where the offence happened, not at the first confirmed match — and the violation is a fact, not a match.
- **Journeys are rebuilt, never appended.** The table stores only ordered sighting ids; distances and confidences are derived on read, so there is no stale copy to keep in step.
- **Straight lines between cameras, not road paths.** The system knows the vehicle was at A then B — not which streets it took. Drawing a road route would claim knowledge we do not have.
- **The route animates hop by hop.** A static polyline carries the same information and none of the effect; this is the demo's closing image.
- **`lon`/`match_score` → `lng`/`score` mapping lives in one function**, rather than asking him to rename.

#### Phase 14 — Watchlist alerts

| Path | Purpose |
|---|---|
| `app/db/queries/incidents.py` | `get_open_for_watchlist` |
| `app/services/watchlist.py` | Compares each new sighting to open incidents |
| `dashboard/src/components/AlertToasts.tsx` | The interrupt |

**Verified:** a violation at Camera 1, then the same vehicle at Cameras 2 and 3 → real cross-camera hits at **0.756–0.905**, logged and stored as matches.

- **Runs on every sighting, not just violations.** That is the whole idea: a vehicle that fled a violation is an *ordinary passing vehicle* by the time it reaches the next camera, and nothing would flag it unless every one were checked.
- **Open incidents are fetched once per frame and capped at 20.** Checking runs per vehicle, so an unbounded list would slow ingest as the demo went on — exactly when it must not.
- **Alerts are stored as normal matches**, so a reappearance is reviewed through the same screen as any other candidate.
- **Only reappearances raise a toast.** Ordinary candidate lists are generated for every incident and would be constant noise.
- **Toasts live in the shell**, so an alert interrupts whatever page is open — otherwise it would fire while someone was looking at the map.

#### Bug found: the application's own logs were invisible

`WATCHLIST HIT`, incident creation, candidate counts — none of it appeared. uvicorn configures only its own loggers, and `logging.basicConfig` is a no-op once handlers exist, so `force=True` was needed. This cost a debugging detour here; during a demo it would have meant no way to see what the system was doing.

**Teammate 1's remaining work:** Phase 10 (space-time sync), 11 (weight tuning on real data), **14 (burst dedup — `dedupe`)**. `dedupe` is the one that still affects us: without it, repeated frames of the same vehicle crowd the candidate list.

**Next:** 17 (demo infra), 18 (deck), 19 (rehearsal), 20 (freeze).

### Wind-up audit — 24 Aug 2026

A full multi-agent audit before the freeze. Phases 17, 18 and 20 were produced in the
same pass. Six issues were found and fixed; two of them would have wrecked the demo.

#### CRITICAL — same-camera candidates got a free perfect score

`pipeline._space_time_score` derives a required speed from `distance / time`. For a
candidate at the **same camera** the distance is 0, so the required speed is 0, so it
returns **1.0 — full marks on the heaviest-weighted signal (0.35) — at any time gap.**

Measured with the real seeded geometry, at realistic CLIP similarity (the measured
0.84–0.93 band, not random vectors):

```
0.7494  unrelated bike, same camera, 120 s  {vehicle 0.91, attributes 0.35, space_time 1.000}
0.6445  THE TRUE MATCH, camera 2, 150 s     {vehicle 0.90, attributes 0.70, space_time 0.451}
```

An unrelated bike that happened to pass the same camera two minutes later beats the
genuine cross-camera match by **0.10**. Since `get_matches_for_incident` is
`ORDER BY score DESC LIMIT 20`, with enough same-camera traffic the true match is not
merely demoted — it is **off the review screen**. That screen is the demo.

Note the second-order effect: a *shorter* gap scores *lower* on space-time, because a
quicker trip needs a higher speed. The signal rewards a vehicle for dawdling. A bike
covering 1.37 km in a realistic 150 s scores 0.451; the same bike taking ten minutes
scores 0.86.

**Fixed** by excluding same-camera pairs on our side, in the two places that build
candidates: `app/services/geo.py` (`build_gate` no longer returns the origin camera) and
`app/services/watchlist.py`. Space-time carries no information about a same-camera pair —
everything is reachable from where it already is — so the honest move is not to ask.

Cost: a vehicle that leaves and returns to one camera is no longer matched. Real, but
worth far less than a correct ranking, and not what the A→B→C demo does.

⚡ **The root fix belongs in `pipeline/matcher.py`** — `distance_m == 0` should score
neutral, not perfect. Raised with Teammate 1.

Regression test: `api/scripts/test_same_camera_fix.py` — asserts the gate excludes the
origin camera, reproduces the exploit through the real scorer to prove it is still live
upstream, and checks the watchlist guard is present.

#### CRITICAL — the watchlist alerted on essentially every vehicle

Same root cause. Because same-camera pairs score a guaranteed 1.0 on space-time, and CLIP
similarity never drops below ~0.84, the **minimum achievable same-camera score was 0.609 —
above the 0.6 alert threshold**. Measured: 20 open incidents produced **20 of 20 alerts on
every single sighting**, roughly 20 match rows and 20 WebSocket events per sighting, about
36,000 rows over a ten-minute run. "Possible reappearance" toasts would have fired over the
journey animation — the closing image.

Fixed by the same same-camera skip. With it, 0.6 separates properly: a true match over a
real hop scores 0.758, a different vehicle over the same hop 0.546.

#### HIGH — three phones out-produced the worker by about 20×

Measured `process_frame` on this CPU: **0.3–2 s per frame**, single serialized worker, so
roughly **0.6–1 fps total**. `BURST_INTERVAL_MS` was 250 ms, so three bursting phones asked
for **12 fps**. The 64-deep queue saturated in about six seconds and then evicted
continuously — dropping exactly the frames a violation is happening in.

Fixed: `BURST_INTERVAL_MS` 250 → **1000**. 1 fps still catches a vehicle crossing the frame
and cuts demand fourfold. Idle rate is unchanged at 1 frame per 2 s.

#### Also fixed

- **The review screen told judges a phase was unfinished** — "No candidates yet — matching
  runs in Phase 11" rendered on every incident with no candidates, which includes the first
  incident of every fresh run. Replaced with what it actually means.
- **`OFFICER_PIN` had a default of `"4321"`**, so a clone with no `.env` silently accepted
  the PIN published in this repo's own documentation. Now required, failing at startup
  beside `DATABASE_URL`.
- **`summary["skipped"]` was counted and discarded** — now surfaced in `/api/frames/stats`.
- Repo junk: `c_language.txt` deleted; `teammate_starter/` marked SUPERSEDED (its
  `types.py` is a divergent earlier draft of the live contract and was actively misleading).
- README now states that copying `.env.example` is required, not optional.

#### Confirmed sound (checked, nothing found)

No silently swallowed exceptions. No unbounded memory growth — every queue, list and
subscriber set is capped. Three phones concurrently are safe: the worker is a single
serialized consumer, so the models are never re-entered. Nothing reaches a phone hardcoded
to localhost. Dashboard builds clean, zero errors and zero warnings.

The watchlist costs **~10 ms per sighting** at the 20-incident cap — 4–10% of frame time,
and hard-capped. It is not, and never becomes, the bottleneck. Inference is.

#### Answered for Teammate 1

- **Yes, our SQL gate applies the 30-second grace.** `min_travel_seconds` in
  `app/services/geo.py` computes `max(0, distance / 60kmh − 30 s)`. Verified against the
  seeded geometry: 1373 m → 52.4 s (82.4 s without grace), 2100 m → 96.0 s (126.0 s).
- **Yes, new `attrs` keys fit.** `attrs` is `jsonb` with no key constraint, so
  `passenger_count` and `helmet_color` need no migration. The review UI renders whatever
  keys arrive.

#### Still open

> **Both resolved on 29 Aug 2026** — see "pipeline_v9 integration" at the end of this file.

- ~~**`tools/replay.py` does not exist.**~~ Delivered and verified against the live API.
- ~~**`pipeline_v9.zip` has not been integrated.**~~ Integrated. The helmet-dict trap never
  fired: he changed `helmet.py` and `orchestrator.py` together. Confirmed on real photos.

---

## pipeline_v9 integration — ✅ complete · 29 Aug 2026

Teammate 1's final delivery, handed over as a folder at `D:\Downloads\project`.
Everything in it that we did not already have is now in the repo, wired, and
verified end to end against the real API. **Phase 19 is unblocked.**

### What arrived, and what was taken

`pipeline/types.py`, `helmet_model.pt` and `yolov8n.pt` were **byte-identical** to
ours, so the contract did not move and the 512-dim embedding needed no
re-verification. `detector.py` differed only by a moved import and a deleted
comment — ours was kept, since its comment explains why the model path is
resolved relative to the file rather than the working directory.

| File | Change |
|---|---|
| `pipeline/dedupe.py` | **New.** Union-find burst dedup — same camera, within 3 s, cosine ≥ 0.95, keep the highest-confidence one |
| `pipeline/__init__.py` | Exports `dedupe`; `is_reachable` now applies the agreed 30 s grace |
| `pipeline/helmet.py` | `check_helmet` returns `{status, confidence}` instead of a bare string |
| `pipeline/orchestrator.py` | Reads the new helmet dict; **never raises** (decode / detect / fingerprint each guarded); fingerprints the whole frame in **one batched CLIP call**; adds `helmet_color` and `passenger_count` |
| `pipeline/fingerprint.py` | Adds `fingerprint_batch` and `_embed_batch`, plus the two new attrs |
| `pipeline/matcher.py` | `_space_time_score` returns **`None`** for `distance_m == 0`, and applies the 30 s grace |
| `pipeline/journey.py` | Per-hop distances rounded once, so the hops shown sum exactly to the displayed total |
| `pipeline/selftest.py`, `smoke.py` | **New.** His contract check and smoke run |
| `tools/replay.py` | **New.** The demo fallback |
| `tools/test_recordings/cam-A/` | **New.** 3 sample frames + `manifest.json` |

### The trap we were warned about did not fire

The wind-up audit flagged that if `check_helmet` started returning a dict while
`orchestrator.py` still compared `status == "no_helmet"`, **violations would
silently stop being detected** — no error, just a demo where nothing is ever
flagged. He changed both files together, so it was never live. Verified anyway on
three real photos: `no_helmet_test.png → [['no_helmet']]`,
`no_helmet_test2.png → [[], ['no_helmet'], [], [], []]`.

### The root fix landed — and both layers are kept

`_space_time_score` no longer returns a free 1.0 for a same-camera pair. It
returns `None`, which `score_candidates` treats as a missing signal and whose
weight it redistributes. Measured through the real scorer against the seeded
geometry:

```
0.6822  THE TRUE MATCH, camera 2, 150 s    {vehicle 0.90, attributes 0.70, space_time 0.5424}
0.5740  unrelated bike, same camera, 120 s {vehicle 0.91, attributes 0.35, space_time 0.0}
```

The true match now wins by 0.108 — it *lost* by 0.108 before. The watchlist floor
for a same-camera pair fell from **0.609 to 0.336**, well clear of the 0.6
threshold.

Our own guards in `app/services/geo.py` and `app/services/watchlist.py` were
**kept**. They are redundant now, and that is the point: the demo should not
depend on an upstream file continuing to behave. `api/scripts/test_same_camera_fix.py`
was rewritten to assert the fixed behaviour on both sides — it had been asserting
that the upstream bug was *still live*, so it correctly went red on integration.

### `dedupe` is wired into ingest

It needs to see the frames just before this one, so:

- **`app/db/queries/sightings.py` → `get_recent_at_camera`** — sightings from one
  camera in the last N seconds. Served entirely by the existing
  `(camera_id, ts DESC)` index.
- **`app/services/pipeline_client.py` → `dedupe`** — the usual boundary wrapper.
  On absence or failure it returns its input **unchanged**: storing a duplicate is
  far cheaper than dropping a real vehicle.
- **`app/services/ingest.py`** — calls it directly after `process_frame`, with a
  5-second lookback (a little wider than the pipeline's own 3 s window, so a burst
  straddling the boundary still clusters). `summary["detections"]` still reports
  the raw count; drops are logged.

Measured against the real database, the same photo three times at one camera:

```
first frame:         detections=8  stored=8
repeat frame (+1 s): detections=8  stored=0
30 s later:          detections=8  stored=8
```

### ⚠️ NEW BUG FOUND AND FIXED — the watchlist alerted on week-old incidents

Found by actually running the replay rather than by reading the code, which is
the entire point of running it.

`get_open_for_watchlist` was capped by `LIMIT 20` but **not bounded in time**. The
required speed is distance over gap, so an incident from six days ago needs a
walking pace to be "reachable" and scores a near-perfect 1.0 on the
heaviest-weighted signal — the same failure mode as the same-camera bug, through
a different door. Measured on the first replay run: **13 watchlist hits at
0.68–0.74**, every one a false alarm against an unrelated vehicle.

Fixed in `app/db/queries/incidents.py`: the query now also requires
`s.ts >= now() - MATCH_WINDOW_SECONDS`, the same 30-minute window the space-time
gate already uses. Beyond it a match is a coincidence, not a reappearance — which
is what that constant already said; the watchlist simply was not asking. The
identical replay afterwards produced **0 hits**.

This matters on the day: incidents accumulate while the demo runs, so without the
bound the false-alarm rate grows the longer the system is up.

### Verified live, not just unit-tested

API started, real pipeline loaded (`/api/health` → `"pipeline": {"real": true}`),
`tools/replay.py` posted all 3 frames using real camera tokens:

```
Sent: 3   Failed: 0
frame -> 6 sighting(s), 3 incident(s)
frame -> 5 sighting(s), 1 incident(s)
plate=BL7350 · plate=SAD426 · plate=UNREADABLE (fingerprint mode)
```

`read_plate` is reading **real plates off real photos** — his Phase 8 working in
production for the first time. `/api/frames/stats` → `processed 3, dropped 0,
failed 0, skipped 0`.

Frame time on this CPU is now **0.5–1.1 s** for 5–8 vehicles, batched
fingerprinting included, against 0.3–2 s before. `BURST_INTERVAL_MS = 1000` stays
the right setting.

### Two small fixes that make replay actually usable

1. **`tools/replay.py` treated every success as a failure.** It checked for HTTP
   200, but `/api/frames` answers **202 Accepted** — it queues rather than
   processes. Every frame would have printed `FAIL`, and a run that was working
   perfectly would have ended `Sent: 0, Failed: N`. On stage, mid-fallback, that
   reads as a dead system. It now accepts 200 or 202.
2. **`replay.py` needs camera tokens and has no database access.**
   `scripts/seed_cameras.py` now also writes `tools/tokens.json`, keyed `cam-A`,
   `cam-B`, `cam-C` — short keys rather than the display names, because they
   double as the recording folder names. **Gitignored**: it is three live secrets.

### Not taken, deliberately

- **His root-level dev scripts** (`test_*.py`, `tune_weights.py`, `color_test.py`,
  `similarity_test.py`, the debug crops, `yolo11n.pt`, his `.venv`). They are his
  working files, they duplicate checks we already have, and `yolo11n.pt` is not
  the model `detector.py` loads.
- **His `docs/stats.md`.** Our `docs/STATS.md` records each number with the command
  that produced it, on this machine; his are from his.
- **No new dependency.** `fingerprint_batch` uses PIL, which torch and ultralytics
  already pull in. `pipeline/requirements.txt` is unchanged.

### Left in the database

The verification replay left **19 sightings and 4 incidents** dated 29 Aug in
`traffic_trace`. Harmless, but they will show up in the feed. Clear them with the
dashboard's **Reset demo** button (sidebar → officer PIN → Unlock → Reset) before
the first rehearsal.

### Next

**Phase 19 — rehearsals.** Nothing blocks it any more:

1. Reset the demo data.
2. Two clean live runs, phones on the hotspot, end to end: phone → incident →
   review → confirm → journey.
3. One replay-fallback run, so the fallback has been rehearsed and not merely
   written:
   `py -3.12 tools/replay.py --folder tools/test_recordings --cameras cam-A --api-url http://<laptop-ip>:8000/api/frames`
   Record real footage at the three chosen locations first — one folder per
   camera, each with its own `manifest.json`.
4. Then Phase 20's remaining physical steps: the git tag and the USB backup.

Unchanged from before: **choose the three real camera locations**, update
`scripts/seed_cameras.py`, and re-run `scripts/download_tiles.py` **while there is
still internet**.

---

## Full pre-demo audit — ✅ complete · 29 Aug 2026

Everything run, not read: the machine check, the whole HTTP flow, the WebSocket,
the dashboard build, a three-phone load test, and a timed measurement of the one
number the demo lives or dies on. **Two real bugs found, one of them fatal.**

New: **`api/scripts/smoke_demo.py`** — 52 checks driving the real API end to end.
`preflight.py` answers *"is this machine ready?"*; this answers *"does the whole
flow still work right now?"* It is destructive (resets twice) and leaves the
database clean, so run it **before** the phones are set up, never during.

```powershell
cd api
.\.venv\Scripts\python.exe -m scripts.smoke_demo
```

Final state: **52 passed, 0 failed.**

### ⚠️ FATAL — the incident never appeared once the phones had been streaming

The demo is: ride past camera A, turn to the screen, the incident is there.
Measured, with three phones streaming a busy street for 30 seconds first:

```
queue depth when the bike passed: 54/64
violation frame POSTed          : 202 accepted
incident on the dashboard       : NEVER, within 180 seconds
```

Not slow — **never**. The frame was accepted, queued, and then evicted by newer
arrivals before the worker ever reached it.

The cause is that the queue depth *is* a delay. At the measured ~1.2 frames/s,
`QUEUE_MAXSIZE = 64` is a **54-second** buffer. A frame entering a full queue has
to survive ~45 seconds of newer frames pushing in behind it, and three phones at
1 fps evict faster than one worker processes. The eviction policy was right all
along — drop the *oldest*, keep what is happening now — the size simply never let
it work.

**Fixed: `QUEUE_MAXSIZE` 64 → 8** in `app/workers/frame_worker.py`, making the
buffer ~7 seconds. Measured A/B on the realistic case (two other cameras
streaming, the bike in shot at camera A for 5 frames, which is what 1 fps gives
you):

| `QUEUE_MAXSIZE` | Queue depth when the bike passed | Incident appeared after |
|---|---|---|
| 64 | 21/64 | **19.3 s** |
| **8** | 7/8 | **5.1 s** |

More frames are dropped — that is the trade, and it is the right one. A high
`dropped` with a low latency is the system working correctly. What matters is
that the frames which *do* get processed are recent.

Sustained three-phone load, 45 s, for the record: 135 posted, 117 processed,
18 dropped, 0 failed, 1.18 frames/s. Demand is ~2.5× capacity and always will be
on this CPU; the queue size is what decides whether that shows up as *lag* or as
*dropped frames*, and dropped frames are survivable while a minute of lag is not.

### ⚠️ The journey contract in `contracts/endpoints.md` was fiction

`GET /api/journeys/{id}` was documented as returning `hops`, `sightings` and a
precomputed OSRM `path`. **None of that was ever built.** The real response is a
flat `stops` list where each stop carries its own hop back to the previous one,
and `JourneyMap.tsx` reads exactly that and draws a straight polyline.

This cost time during this very audit: the first run reported the journey as
broken because it was checking the documented shape. Anyone debugging against it
tomorrow reaches the same wrong conclusion about the demo's closing image.

Corrected in `contracts/endpoints.md`, with the note that `stops` use **`lon`**,
not `lng` — Teammate 1's naming, mapped in `services/journeys.py`.

Verified the closing image really works:

```
1. Camera 1 — Shahrah-e-Faisal   25.011,  67.0403   hop 0.0 km      conf 1.00  crop ✓
2. Camera 2 — Tipu Sultan Rd     25.0205, 67.049    hop 1.373 km    conf 0.84  crop ✓
3. Camera 3 — Karsaz             25.002,  67.053    hop 2.096 km    conf 1.00  crop ✓
total 3.469 km over 450 s — 3 of 3 stops positioned and drawable
```

### Two smaller fixes

- **`start_demo.ps1` did not write `tools/tokens.json`.** It already reads the
  tokens out of the database to print them, so it now writes the file in the same
  step. Without it the replay fallback authenticates with nothing and every frame
  is rejected — discovered on stage, at the worst possible moment. The fallback is
  now armed on every startup rather than depending on someone having re-run
  `seed_cameras.py` since the last reseed.
- **`PROGRESS.md` claimed the queue "drops the newest frame when full".** It is
  and always was the *oldest*, deliberately. Corrected, along with the four
  places in `RUNBOOK.md` and `DEMO_SCRIPT.md` that quoted the old size of 64.

### Checked and sound

| Area | Result |
|---|---|
| `preflight.py` | 32 passed, 1 warning (C: has 4.6 GB free — tight but fine), 0 failed |
| All 7 pipeline functions | real, loaded from `pipeline/`, `selftest.py` 13/13 |
| Auth | no token, bad token, no PIN, wrong PIN — all correctly 401 |
| CORS | hotspot ranges allowed (`192.168.x`, `10.x`, `172.16-31.x`, any port); a public origin is refused with no allow-origin header |
| Error paths | unknown id 404, bad uuid 422, empty frame 400, oversize 413 |
| A non-JPEG body | accepted, then survived by the worker — `failed` stays 0 |
| Ranking | 14 candidates, correctly sorted, 4-signal breakdown, **no same-camera rows** on live data |
| WebSocket | all five event types fired: `connected`, `sighting`, `incident`, `match_suggestion`, `match_decision`, `journey_update` |
| Evidence serving | `crop_url` → 200, real JPEG bytes |
| Dashboard build | `next build` clean, 0 errors, all 8 routes |
| Offline tiles | 528 tiles, z13–17, covering lat 24.986–25.036 / lon 67.014–67.066 — **all three cameras inside the cached area** |
| Retention sweeper | correct, and inert during a demo (48 h threshold) |
| `start_demo.ps1` | parses clean; refuses to report READY on a stub pipeline |

### Note, not a fault

`OFFICER_PIN` is `4321`, which is the PIN printed in `docs/RUNBOOK.md`. Consistent,
and fine for a demo where anyone holding the laptop also holds the runbook. Change
both together if the laptop is ever left unattended.

### Left clean

`cameras 3 · sightings 0 · incidents 0 · matches 0 · journeys 0`, evidence empty.
The audit's camera-registration test created a throwaway camera; it was removed,
and `smoke_demo.py` now removes its own. **A fourth camera is not cosmetic** — it
changes the reachability geometry the gate enforces and puts a stray pin on the
map.

---

## 🔴 The offline map was never real — found during the first live phone test · 30 Aug 2026

Three phones scanned a photo, the pipeline worked perfectly (violations detected,
plate `AX7110` read, 6–7 candidates each), and then **Live map rendered a wall of
"Access blocked / 403"**.

### What was actually on disk

All **528 cached tiles were byte-identical**, 6987 bytes each — and their MD5
matched a fresh fetch from `tile.openstreetmap.org` exactly. Not one real map tile
had ever been downloaded. The cache was 528 copies of OSM's *"App is not following
the tile usage policy"* image.

OSM enforces its no-bulk-download policy by answering **HTTP 200 with that image**
rather than an error status. `download_tiles.py` checked the status code, saw 200,
and wrote the placeholder to disk 528 times without complaint.

### Why nothing caught it

Every check counted files. `preflight.py` said *"528 tiles cached — PASS"*.
`start_demo.ps1` said *"528 tiles cached"*. The 29 Aug audit confirmed the tile
coordinates covered all three cameras — which was true, and useless, because each
of those correctly-named files was the same error image. **Nothing ever looked at
the bytes**, and the failure is invisible until a map is actually rendered on a
screen.

### Fixed — on the second attempt

**Carto was tried first and also failed, differently.** Its CDN returned real map
data, so every byte-level check passed — 714 tiles, 629 distinct images, all three
cameras covered, `preflight` green. Then the map rendered **"API KEY REQUIRED ·
carto.com/basemaps/apikey"** stamped diagonally across every tile. Real streets
underneath, completely unshowable.

That is the same lesson twice in one evening: **a hash check proves the tiles are
different from each other, not that they are usable.** The only check that catches
a watermark is opening the image and looking at it, which is what was done next —
a downloaded tile was rendered and inspected directly, and only then accepted.

- **Provider is now `tile.openstreetmap.de`** (the German OSM community server),
  which serves the standard OSM style cleanly, with no key and no watermark.
  Verified by eye on a cached tile: street geometry, building outlines and labels
  (`Kings Dreams Villas`, `St. 38`) all present and unobstructed.
- Cache: **714 tiles, 652 distinct images, 5.0 MB**, all three cameras covered at
  zoom 13–17.
- **`download_tiles.py` now verifies what it downloads.** It rejects non-PNG
  payloads, aborts if the first 8 tiles come back byte-identical (the signature of
  a provider refusing bulk downloads), and at the end re-hashes the whole cache —
  so a poisoned cache from an earlier run cannot survive by being skipped.
- **`preflight.py` now hashes the tiles**, failing when a cache has fewer distinct
  images than roughly one per fifty files, and separately confirms each seeded
  camera has a tile at every zoom 13–17.
- Old cache deleted, re-downloaded: **714 tiles, 629 distinct images**, all three
  cameras covered at every zoom.

`preflight.py` is now 34 passed / 0 failed.

### The lesson worth keeping

A count is not a check, and neither is a hash. Three green checks agreed the cache
was fine while every byte of it was an error image; the next provider passed every
automated check and was still unusable. For anything cached from a network source,
the only sufficient check is rendering it and looking — everything cheaper than
that failed here, twice, in the same evening.

### Note for the dashboard

`next start` indexes `public/` at startup, so newly downloaded tiles 404 until the
dashboard process is restarted. Restarting is enough; no rebuild is needed.
Browsers also cache the old blocked images aggressively — a hard reload
(Ctrl+Shift+R) is required after re-downloading.

---

## The product boundary, and a review screen that asks one question · 30 Aug 2026

Two changes driven by a single realisation from Daniyal: **this is a feature
upgrade to an existing ANPR deployment, not a replacement for one.** Everything
below follows from that sentence.

The demo was pushed back, so these were built properly rather than patched in.

### 1. Fingerprint matching now runs only when the plate cannot be read

A readable plate is a solved problem. The existing system issues the ticket from
the plate alone; running gating, ranking and a review queue on top of it adds
cost and offers an officer a second opinion nobody asked for.

So the expensive half is gated:

| | Plate read | Plate unreadable |
|---|---|---|
| Sighting stored | ✅ | ✅ |
| Incident opened | ✅ | ✅ |
| Space-time gate + ranking | ❌ skipped | ✅ |
| Watchlist re-detection | ❌ skipped | ✅ |
| Journey | ❌ | ✅ on confirm |

- `services/ingest.py` — `run_matching` is skipped when `plate` is truthy, and
  logs *"plate X read - handed to ANPR, fingerprint matching skipped"*.
- `db/queries/incidents.py` — `get_open_for_watchlist` gained
  `AND i.plate_text IS NULL`, so a plate-read incident never costs ~10 ms on
  every passing vehicle to re-detect something the plate already identified.

**What is deliberately NOT gated: fingerprinting every vehicle.** That is not the
feature, it is the feature's precondition. A vehicle whose plate is unreadable at
camera C must be matched against its earlier appearances at A and B — and when
those were recorded, nobody knew they would matter. Fingerprints have to exist
*before* the violation, so they cannot be conditional on one. It is also ~71% of
frame time, and that cost is the price of the whole product.

Verified in both directions against the live API:

```
plate A3VV807 read     -> 0 candidates computed, 0 incidents watched
plate unreadable (x3)  -> 2 candidates each, all from OTHER cameras,
                          3 of 3 incidents on the watchlist
```

### 2. The review screen asks one question instead of showing a search result

It rendered every candidate as a grid of small cards. That showed the work but
not the decision — a grid of eight bikes is a search result, not a question.

Now: the violation on the left, **one** candidate on the right, both large, with
the score breakdown as labelled bars (`vehicle shape`, `rider`, `colour`,
`time + distance`) and the time gap phrased as *"3 minutes later"*. Two buttons:
**Same vehicle** / **Not the same**. Underneath, a filmstrip of every candidate,
clickable, marked confirmed / rejected / current.

Three details that matter:

- **After a confirm, the next candidate is picked from a camera not yet
  confirmed.** At 1 fps one pass produces several frames of the same bike at the
  same camera; without this the officer clicks through four near-identical photos
  before the route grows a single hop. Now it goes A → B → C, which is also
  exactly how the demo is narrated.
- **The current candidate is tracked by id, not by list index.** The undecided
  list shrinks on every decision, and an index into a shrinking list silently
  skips entries — the old code had that bug.
- **A plate-read incident shows the plate large and says "handled by ANPR"**,
  rather than an empty candidate list that reads as a failure.

### 3. One stop per camera visit on the journey

Confirming several sightings of one camera pass produced a stop each: a clean
A → B → C route rendered as **nine** stops, six of them stacked on the same point
with a 0.0 km hop, and the map animation stuttering through them.

`services/journeys.py` now collapses *consecutive* same-camera stops into one
visit, keeping the highest-scoring sighting as the evidence and the earliest
timestamp as the arrival. Non-consecutive repeats survive, so a vehicle that
leaves and returns to a camera still shows both visits.

```
before: 9 stops, 3.122 km    after: 3 stops, 3.122 km
```

The officer can now confirm as many candidates as they like and the route stays
readable — which matters on stage, where nobody is clicking carefully.

### 4. ⚠️ A BOM would have killed the replay fallback

Caught by a test failing with `Expecting value: line 1 column 1`.

The `start_demo.ps1` change from the 29 Aug audit wrote `tools/tokens.json` with
`Out-File -Encoding utf8`. In Windows PowerShell 5.1 that **prepends a UTF-8 BOM**,
and Python's `json.load` on a plain `open()` treats those three bytes as a syntax
error. So on demo morning `start_demo.ps1` would have written a tokens file that
`tools/replay.py` — the stage fallback — could not read at all.

The irony is exact: the fix that armed the fallback is what would have disarmed it.

Fixed on both sides, because either alone leaves a trap:

- `start_demo.ps1` writes via `[System.IO.File]::WriteAllText` with
  `UTF8Encoding($false)`, which omits the BOM.
- `tools/replay.py` and `scripts/smoke_demo.py` read with `encoding="utf-8-sig"`,
  which tolerates one however the file was produced.

### Demo consequence worth knowing

**With the gate on, the bike used on stage must have an unreadable plate**, or the
feature never engages and the review screen correctly says "handled by ANPR".

Measured on the test images:

| Image | Plate | Path |
|---|---|---|
| `no_helmet_test.png` | `None` | ✅ our feature |
| `no_helmet_test2.png` | `A3VV807` | ANPR |
| `street3.jpg` | mixed — some read, some not | **both on one screen** |

`street3.jpg` and `tools/test_recordings/cam-A/frame_002.jpg` produce *both* kinds
of incident from a single frame. That is the strongest thing to put on stage: one
photo, two bikes, one handed to the existing system and one that only this feature
can follow.

### Verification

- `scripts/smoke_demo.py` — **52 passed, 0 failed** after both changes.
- Dashboard `next build` — clean, TypeScript passed, all 8 routes.
- Product boundary tested in both directions against the live API.
- Journey re-checked: 3 stops, one per camera.

---

## Real street footage exposed three more · 30 Aug 2026

Daniyal played traffic video into the three phone cameras — one motorcycle
riding past parked cars — and the dashboard produced a route with **two stops
instead of three**, and a candidate list that was mostly cars.

His data told the story exactly:

```
53 sightings stored:  40 cars · 8 motorcycles · 5 trucks
camera 3 incident:    19 candidates, of which 3 were motorcycles
camera 1 incident:     4 candidates  ->  route stopped at 2 stops
```

### 1. Cars were taking the review screen from the bike

`CANDIDATE_TOP_K` is 20. Cars filled **16 of those 20 slots** for a motorcycle
incident, so the bike that mattered was competing with parked traffic for a
place in front of the officer.

The only violation this system detects is `no_helmet`, which no car, bus or
truck can ever commit. Every other class was cost with no possible payoff.

**Fixed in `pipeline/detector.py`: `VEHICLE_CLASSES = {"motorcycle"}`.** They are
never returned, so never fingerprinted, stored, ranked or watched.

The speed win is the same change: fingerprinting is ~71% of frame time and it now
runs on a fraction of the objects.

| Scene | Before | After |
|---|---|---|
| `street1.jpg` (8 vehicles, 1 bike) | ~0.76 s | **0.33 s** |
| `street4.jpg` | ~0.65 s | **0.35 s** |
| `street2/3.jpg` (5 real bikes) | ~1.0 s | ~1.0 s — the work is real |

On ordinary traffic that is roughly **3× the throughput**, which directly relieves
the ingest-latency problem from the 29 Aug audit.

⚠️ **A video with no motorcycles now produces nothing at all.** That is intended,
but it will look like a broken system to anyone who does not know.

### 2. An incident never saw the cameras the vehicle reached *later*

The camera 1 incident opened at 19:46:16. The same bike reached camera 2 at
19:47:36 and camera 3 at 19:49:01 — **after** matching had already run. Matching
happens once, at ingest, so those sightings were never candidates.

The watchlist is supposed to cover this, and partly did, but it only adds a match
when the score clears its 0.6 alert threshold. A genuine match scoring 0.55 never
reached the review screen, so the officer could not confirm a third stop even
though the evidence was in the database.

**Fixed: `services/matching.py` gained `refresh_candidates`, called from
`GET /api/incidents/{id}`.** Opening an incident re-ranks it against everything
recorded since. `save_matches` is an upsert with `WHERE matches.decision IS NULL`,
so re-running never disturbs a decision already made. Costs ~40 ms.

Verified on the same scenario: the first incident now offers **5 candidates from
camera 2 and 5 from camera 3**, and the route reaches all three stops.

```
before:  4 candidates, 2 stops, scores 0.60 / 0.56
after:  10 candidates, 3 stops, scores 0.92 / 0.89
```

### 3. ⚠️ `cam-A` meant a different camera depending on who wrote the file

Found while investigating the above. **The two writers of `tools/tokens.json`
ordered the cameras differently:**

```
seed_cameras.py   ORDER BY created_at  ->  cam-A = Camera 3    (on this machine)
start_demo.ps1    ORDER BY name        ->  cam-A = Camera 1
```

Whichever ran last decided what `cam-A` meant. `replay.py` would then submit the
camera-A recording under a different camera's token — wrong position, wrong
distances, a route drawn between the wrong points, and **no error anywhere**. The
fallback would appear to work perfectly and be quietly wrong.

`created_at` order is not name order and was never guaranteed to be; on this
database it happened to be exactly reversed. **Both now `ORDER BY name`**, which
is stable and is what a human reading "Camera 1" expects. Verified: the two
writers now produce identical files.

### 4. Camera positions drift, and a test was hardcoded around them

The `/camera` page lets a phone report its own position, which is the point — so
a field test moves the cameras. After Daniyal's, camera 2 and camera 3 were
0.9–2.4 km from where `seed_cameras.py` put them.

`scripts/test_same_camera_fix.py` hardcoded a 150-second gap, comfortable at the
seeded 1.37 km and a 53 km/h dash at the new 2.23 km. It failed for a reason that
had nothing to do with what it tests.

It now derives the gap from the actual spacing at 25 km/h — ordinary city riding —
so it tests the logic wherever the cameras happen to be, and prints the geometry
it used.

### Verification

- `scripts/smoke_demo.py` — **52 passed, 0 failed**
- `pipeline.selftest` — 13/13
- `scripts/test_same_camera_fix.py` — all checks pass, geometry-independent
- Daniyal's exact scenario replayed: motorcycles only, 3-stop route, all candidates bikes

---

## One bike became two cards · 30 Aug 2026

Daniyal pointed a phone at one motorcycle. The feed showed **two `no helmet`
incidents, both the same bike**, 5 seconds apart.

```
4 sightings of one bike at camera 1, 20:17:20 -> 20:17:26
2 of them were flagged for no_helmet  ->  2 incidents
```

An incident was opened per violating *sighting*, not per *vehicle pass*. At 1 fps
a bike is in shot for several frames and the helmet model flags more than one of
them, so a single rider filled the officer's queue with duplicate cards. On stage
one pass would have produced five or six identical cards.

`dedupe` did not catch it and could not have: its window is 3 s and these were
4.6 s apart, and its threshold is 0.95 while these scored 0.87.

### No visual signal can separate these — measured

Across the four frames of that one bike at that one camera:

| Signal | Range across frames of the SAME bike |
|---|---|
| CLIP cosine | **0.865 – 0.932** |
| Colour-histogram overlap | **0.32 – 0.78** |
| Dominant colour name | flipped `gray` → `blue` → `gray` |

Both sit inside the band two *different* bikes produce (0.84–0.93 for CLIP, per
the Phase 7 measurement). The colour histogram — nominally the stronger signal at
weight 0.30 — was the worse of the two here, because the crop reframes as the
bike moves. **A similarity threshold would have been false confidence, not a fix.**

### So the rule is time, not appearance

`db/queries/incidents.py` gained `find_open_at_camera`, and `services/ingest.py`
consults it before opening an incident: same camera, same violation, within
`INCIDENT_MERGE_WINDOW_SECONDS = 30`. If one is already open, the later frames are
still stored as sightings — they are evidence and candidate material — but no
second incident is created.

One camera watches one spot, and one violation event happens there at a time.
That is a real property of the deployment, and it discriminates where the pixels
do not.

Marked `ponytail:` in the code with its ceiling: **two genuinely different
offenders passing the same camera within 30 s become one incident.** That is a
real cost, accepted because a queue full of duplicates is the worse failure for a
product whose whole value is an officer's attention.

### Verified

```
A. six violating frames at one camera over 6 s   -> 1 incident   (was 2+)
B. same bike at a second camera 5 min later      -> its own incident
C. a separate pass at camera 1, 400 s later      -> its own incident
D. cross-camera candidates                       -> still found
```

`scripts/smoke_demo.py` — 52 passed, 0 failed.

### Not done

The incident keeps the **first** flagged frame, not the best one. In this sample
the later frame had higher detection confidence (0.65 vs 0.55) and would have made
a clearer card. Storing the best crop means updating the incident's sighting after
the fact; worth doing if the demo crop ever looks poor, not worth it now.

---

## The evidence photo now shows the rider · 30 Aug 2026

Daniyal, looking at a review screen: *"ye sirf vehicle ki pic le raha hai kyun?
Majority bikes to aik jaisi he dikhti hain. Agar us pe betha banda bhi saath ho
to zahir si baat hai aasani ho jayegi."*

He is right, and it is the sharpest product point of the day. The officer's whole
job on that screen is **is this the same one?** — and the picture being compared
had the answer cropped out of it.

YOLO's motorcycle box covers wheels, frame and seat and stops below the person.
So the evidence crop was a machine with the rider's head sliced off, and one
150cc commuter bike looks exactly like the next one.

### Measured on real street footage (`street3.jpg`)

| | Crop height |
|---|---|
| Vehicle box alone | 109 px |
| Vehicle + rider | **197 px** — 1.81× |

Across five motorcycles in that frame the crop grew 1.49–1.81×. Looked at
directly rather than measured: the old crop is an anonymous scooter, the new one
shows a rider in a brown shirt, their build, and how they sit. That is what a
person recognises.

### How

`rider_bboxes` already existed — the detector computes it and the helmet check
uses it — it was simply dropped from `process_frame`'s output.

- `pipeline/orchestrator.py` — returns `rider_bboxes` per detection.
- `services/pipeline_client.py` — an alias entry and normalisation, so a rename
  upstream fails loudly rather than silently.
- `services/evidence.py` — `save_crop(..., also=[...])` crops the **union** of the
  vehicle box and the rider boxes. A malformed rider box falls back to the vehicle
  box rather than costing the evidence photo.
- `services/ingest.py` — passes them through. A car has no rider box, so `also` is
  simply empty.

**`sightings.bbox` is unchanged** — that stays the detection. Only the picture a
human looks at got wider. Embeddings are unaffected: the pipeline computes
`veh_emb` and `rider_emb` from its own crops, not from this one.

### Also fixed: a flaky check in smoke_demo

`drain()` waited for `queued == 0`, but the last job is off the queue and still
running inference at that moment, and `processed` only increments afterwards. It
read the counter mid-flight and reported a frame missing that was merely not
finished — one run failed, the next passed with no change. It now waits for the
queue to be empty **and** the processed count to stop moving.

A test that cries wolf is worse than no test, particularly on a demo morning.

### Verified

```
pipeline.selftest        13 passed, 0 failed
one pass = one incident  A, B, C, D all pass
scripts/smoke_demo.py    52 passed, 0 failed
```

---

## One rider, one offence, one case · 30 Aug 2026

Daniyal, watching the same bike reach camera 2: *"do case ban gaye. Hona to ye
chahiye tha ke agar police wala bole 'not same', tab case bane."*

And separately: *"sirf clear images ko consider karo, har bas-ari-teri image ko
nahi."*

Both are right, and the first is a genuine model change: an incident was one
*violating sighting*, and it should be one *offender's offence*.

### The rule now

```
violation detected
├─ already matches an OPEN case at another camera, strongly?
│    -> attach as a candidate. No second case.
└─ otherwise
     -> open a case

officer says "not the same vehicle"
     -> that sighting becomes its own case, right then
```

Nothing is lost by not opening a case: the sighting is stored with its
violations, so rejecting the match promotes it. **The officer's judgement decides
whether it is one offender or two, which is where that decision belongs.**

- `sightings.violations text[]` added — a sighting now records what was seen
  wrong with it, which is what makes promotion-on-reject possible.
- `services/matches.py` — new. `promote_rejected` opens the case, in fingerprint
  mode, and runs matching for it immediately.
- `routes/matches.py` — a reject calls it and publishes the new `incident` event.

### ⚠️ The first version of this swallowed real offenders

Suppression was gated on *any* watchlist alert, and the watchlist alerts at 0.6.
Those are two different questions and using one number for both was the bug.
Measured through the live fuser:

| | Fused score |
|---|---|
| The same bike at another camera | **0.9158** |
| Six genuinely different helmetless riders | 0.685 · 0.687 · 0.695 · 0.715 · 0.741 · 0.749 |

**Every one of the six cleared 0.6.** Each was filed as the bike already on record
and never investigated — an offender walking free, silently, which is far worse
than the duplicate cards the change was meant to fix.

Fixed with a separate, much higher bar: `INCIDENT_GROUPING_SCORE = 0.85`, above
every different rider measured and below the true match, with room either side.
`ponytail:` in the code notes it is one scene's worth of evidence, and that the
officer's reject is the safety net.

The regression test now includes exactly this case, so it cannot come back
unnoticed.

### Only images worth looking at

`MIN_VEHICLE_HEIGHT_PX = 96`. Below that a crop is a smudge — CLIP resizes
everything to 224x224, so a 52x68 box of a distant bike is upscaled mush whose
embedding means nothing, while still taking a candidate slot and an officer's
attention.

Chosen from real footage, not guessed. One session at 960px capture width:

```
too far   60, 68, 68, 71 px tall
usable   145, 157, 213, 214 px tall
```

Absolute pixels on purpose: it measures how much real detail the model receives,
which is the thing that matters, and does not drift with frame size.

### New: `api/scripts/test_case_grouping.py`

Six scenarios, because this is now the most intricate rule in the product and the
easiest to break by accident:

```
[1] five flagged frames of one pass          -> ONE case
[2] the same rider at cameras 2 and 3        -> still one case, both as candidates
[3] officer rejects one                      -> it becomes its own case
[4] officer confirms another                 -> route builds
[5] the same rider again 15 min later        -> still no new case
[6] a DIFFERENT helmetless rider             -> gets their own case
```

Test frames live in `tools/test_recordings/` (`violation.jpg`, `other_rider.jpg`).

### ⚠️ And a test bug that cost an hour and looked exactly like a product bug

Case [6] failed twice with "a different offender was swallowed", and it was not
true. The wait helper returned before the frame had finished:

```
frame leaves the queue  ->  queued == 0
inference runs (~1 s)   ->  processed still shows the old value
two reads a second apart both see the old value  ->  "done"
```

So the database was read before the work landed. The earlier "fix" for this in
`smoke_demo.drain()` had the identical hole — waiting for the counter to *stop
moving* is indistinguishable from it *not having started*.

Both now wait for an exact total: `processed >= before + frames_posted`. Counting
is the only honest signal; quiet is not.

Worth remembering: **the first two times this test failed, the code was right.**
A test that lies costs more than no test, and both lies here were the same
mistake made twice.

### Verified

```
scripts/test_case_grouping.py   all six scenarios pass
scripts/smoke_demo.py           52 passed, 0 failed
scripts/test_same_camera_fix.py all pass
pipeline.selftest               13/13
```

---

## Grouping by score does not work — the officer decides · 30 Aug 2026

Daniyal ran the same rider past cameras 1 and 2, confirmed the match, and still
got **two cards**. The automatic grouping added earlier that same day had not
fired.

His data said why, and it overturned the previous fix:

| | Fused score |
|---|---|
| **The same rider**, cameras 1 → 2, real footage | **0.5472 · 0.5363 · 0.5363 · 0.5158** |
| Six **different** riders (synthetic, same image at both cameras) | 0.685 – 0.749 |

**The same vehicle scores LOWER than different ones.** That is not a threshold
that needs tuning, it is the wrong way round, and no number separates them.

The earlier measurement of 0.9158 for "the same bike" was taken by posting the
*identical image* at both cameras. Two crops of one bike from two real cameras
are nothing like identical — different angle, distance, lighting — and score
0.52-0.55. **The measurement was of the test, not of the world**, and every
conclusion drawn from it was wrong.

Note what is dragging it down: `space_time` scores 0.22-0.28 because cameras 1
and 2 are 0.92 km apart and he crossed them in ~44 s, which the scorer reads as a
45 km/h dash and barely plausible. `vehicle` 0.82-0.90 and `rider` 0.78-0.88 are
both high — but they are high for everything, which is the whole problem.

### So grouping moved to the only signal that knows

- **Every violation opens a case again.** The score-based suppression is gone. At
  ingest nothing can honestly say whether two helmetless riders are one person,
  so nothing pretends to.
- **Confirming a match folds the duplicate away.** `incidents.merged_into` was
  added; the feed skips merged rows. Confirming is the officer stating the two
  are one vehicle, so that is when the second card disappears.
- `promote_rejected` is gone with the suppression that created the need for it —
  a case that was never suppressed needs no promoting.

The row is never deleted, so the merge is a presentation decision resting on a
human's judgement rather than a guess that can be wrong in either direction.

### What the officer now sees

```
[1] five frames of one pass at camera 1        -> 1 card
[2] the same rider at cameras 2 and 3          -> 3 cards, each holding the others
[3] open the camera 1 case                     -> both other cameras as candidates
[4] confirm camera 2   3 cards -> 2
    confirm camera 3   2 cards -> 1            -> ONE card for one offender
[5] the route                                  -> all three cameras
[6] a different helmetless rider               -> always its own card
```

Three cards briefly exist before review, which is honest: until a human looks,
the system genuinely does not know they are one person. It collapses as the
officer works, which is also the demo's story.

### Reversed in one day, and worth saying plainly

The morning's design — suppress on a watchlist hit — was built, found to swallow
six real offenders, "fixed" with a higher threshold, and then shown by real
footage to be unworkable at any threshold. Three iterations, and the thing that
settled it was **his footage, not my test images.**

The lesson is not about thresholds. It is that a similarity measurement taken on
duplicate inputs tells you nothing about distinguishing real ones, and every hour
after that was spent tuning a number that never had a value that worked.

### Verified

```
scripts/test_case_grouping.py   all six scenarios pass
scripts/smoke_demo.py           52 passed, 0 failed
scripts/test_same_camera_fix.py all pass
```

---

## The score was ranking by the wrong thing · 30 Aug 2026

Daniyal, looking at a review screen offering three candidates all scoring 0.69,
none of which was his bike:

> *"Camera 1 me jo nazar aya hai wo kitna different hai un se jin se match kar
> raha hai. Agar saari pics tum police ko de rahe ho, to tumhara kya kaam?
> Phir wo khud he dhoond lega."*

Exactly right. The product exists to **narrow** the search. Handing over twenty
lookalike bikes is the work it is supposed to remove.

### His own labelled data said why

He had already confirmed the true matches on an earlier case, so for once there
was ground truth:

| Signal | Confirmed same rider | Different bike |
|---|---|---|
| vehicle (CLIP) | 0.90 – 0.94 | 0.85 – 0.90 | overlapping |
| rider (CLIP) | 0.87 – 0.95 | 0.83 – 0.92 | overlapping |
| **colour** | **0.54 – 0.67** | **0.35** | ✅ separates |
| **time + distance** | **0.51 – 0.52** | **0.79** | 🔴 **inverted** |
| **fused** | 0.660 – 0.712 | 0.687 – 0.692 | useless |

**The heaviest-weighted signal was pointing the wrong way.** `space_time` gave the
wrong bikes 0.79 and the right one 0.51 — because the impostors happened to drift
past four minutes later at a comfortable pace, while the true match crossed a
0.92 km hop in 84 seconds, which the scorer reads as suspiciously fast. At weight
0.35 it outvoted colour, the one signal that actually knew.

### The fix: space-time is a gate, not an identity

It answers *"could a vehicle have got here in time"*. The SQL gate has already
asked and answered that before anything reaches the scorer — so scoring it again
double-counts the gate, with the heaviest weight, using an inverted signal.

`build_scoring_payload` no longer sends `distance_m` / `time_gap_seconds`.
`score_candidates` already treats a missing distance as a missing signal and
redistributes its weight, so **no change to `pipeline/matcher.py` was needed** and
the division of labour lands where it belongs: **the gate owns plausibility, the
scorer owns appearance.**

`services/watchlist.py` had the same flaw and now uses `is_reachable` as a filter
before scoring, rather than feeding distance into the score.

Re-scored on his real data, through the live scorer:

```
                      WITH time+dist    WITHOUT
different bike            0.6916         0.6373
TRUE match                0.6604         0.7411
different bike            0.6916         0.6378
TRUE match                0.7119         0.8172
different bike            0.6873         0.6317
TRUE match                0.6773         0.7612

true  0.741 - 0.817      false 0.632 - 0.638      separation +0.103
```

Overlapping before, cleanly separated after.

### And now a threshold is possible

`MIN_CANDIDATE_SCORE = 0.70`, sitting in that gap. Candidates below it are not
stored and never reach an officer. When nothing clears it the review screen says
so plainly:

> **No vehicle close enough to ask about** — other cameras recorded vehicles, but
> none looked enough like this one to be worth your time. Narrowing that down is
> the job; showing you every passing bike would not be.

That message matters: a silent empty list reads as breakage, and this is the
system doing its job.

`ponytail:` one session's labels. If a true match is ever missed, this constant is
the first place to look — and because the screen states plainly that it excluded
everything, a miss is visible rather than silent.

### Why this was findable only now

The signals were never re-examined against labelled data until he confirmed
matches by hand and then complained about the ones he had not. Every earlier
measurement in this file was taken on synthetic pairs — identical images, random
vectors — and none of them could have shown an inverted signal, because none of
them varied the thing that inverted it.

### Verified

```
scripts/test_case_grouping.py   all six scenarios pass
scripts/smoke_demo.py           52 passed, 0 failed
scripts/test_same_camera_fix.py all pass
```

---

## Bench-testing override: the gate stops demanding travel time · 30 Aug 2026

Daniyal is testing alone, at home, moving one video past three phones. The gate
demanded 25–116 s between cameras depending on the pair, so every run meant
standing around for two minutes between each one.

`GATE_MAX_REQUIRED_GAP_SECONDS = 2.0` in `app/core/constants.py` caps what the
gate may demand:

```
        distance    was      now
1 -> 2   0.92 km    25.3s    2.0s
1 -> 3   2.43 km   115.7s    2.0s
2 -> 3   2.23 km   103.6s    2.0s
```

Applied inside `geo.min_travel_seconds`, so the SQL gate and the watchlist pick it
up from one place and cannot disagree.

**It does not touch scores.** Space-time came out of the identity score earlier
today, so how fast the vehicle appears no longer moves any percentage — the cap
only decides whether a candidate is offered at all. That was his actual worry and
it was already handled.

Verified end to end at his working pace: the same video sent to cameras 1, 2 and 3
**five seconds apart** now produces candidates from both other cameras.

### ⚠️ It invalidates the pitch's central claim while it is on

*"A vehicle cannot be 3 km away four seconds later"* — with this set, it can.

So `scripts/preflight.py` now **fails** while the override is active, rather than
warning:

```
Bench-testing overrides
  FAIL  REACHABILITY GATE IS OVERRIDDEN  -  the gate demands at most 2s between
        any two cameras, so 'a vehicle cannot be 3 km away seconds later' is NOT
        true right now
        fix: set GATE_MAX_REQUIRED_GAP_SECONDS = None in api/app/core/constants.py
```

A red line on the pre-demo check is the only thing that reliably stops a testing
shortcut reaching a stage. **Set it to `None` before any demo.**

Agreed as temporary: it becomes dynamic later, presumably per-camera or from a
configured deployment profile. Nothing has been built for that yet — YAGNI until
the shape is known.

### Verified with the override on

```
five-second gap across three cameras   candidates from both, as intended
scripts/smoke_demo.py                  52 passed, 0 failed
scripts/test_case_grouping.py          all six scenarios pass
scripts/test_same_camera_fix.py        all pass
scripts/preflight.py                   34 passed, 1 warning, 1 FAILED (by design)
```
