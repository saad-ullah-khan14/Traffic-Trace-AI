# File Map — what every file does

> Updated at the end of every phase. `PROGRESS.md` records **what was decided and why**; this file records **what each file is for**.
>
> **Last updated:** 23 Aug 2026 (wind-up complete — phases 17, 18, 20 written; only 19 remains)
>
> **New here?** Read `PROGRESS.md` first — its section 0 has the run commands,
> credentials, working rules, and what is left to do. This file is the map of
> what each file is for.

Status key: ✅ built · 🔜 planned, with the phase that creates it · 👤 Teammate 1 owns it · ⚙️ auto-generated

---

## Root

| File | Status | What it does |
|---|---|---|
| `README.md` | ✅ | How to install and run the project. First thing a new person reads |
| `HANDOFF.md` | ✅ | **Start here in a new session.** Current state on one page: how to run it, what is open, and the measurements not to re-derive |
| `PROGRESS.md` | ✅ | Phase-by-phase log: what was built, what was decided, why. Written to be pasted into another AI session as context |
| `FILES.md` | ✅ | This file |
| `start_demo.ps1` | ✅ | Cold laptop → running system in one command. Verifies DB, venv, `.env`, tiles, prints the LAN IP + camera tokens + Chrome-flag origin. Refuses READY if the pipeline is a stub |
| `.gitignore` | ✅ | What git must never upload — `.venv/`, `node_modules/`, `.env` passwords, evidence photos, map tiles, **and `dashboard/`** (its own repo). The two model weights the pipeline loads are deliberately un-ignored |

---

## Two repositories

| Folder | Repo |
|---|---|
| `Traffic_Trace/` (this one) | **Traffic-Trace-Backend** — api, pipeline, contracts, tools |
| `Traffic_Trace/dashboard/` | **Traffic-Trace-Frontend** — Next.js |

They must be cloned side by side in this layout: `api/` imports `pipeline/` as a
sibling, and `scripts/download_tiles.py` writes into `../dashboard/public/tiles`.
`dashboard/` is gitignored by the backend repo so the two never track the same file.

---

## `contracts/` — the shared agreement

Neither side changes these alone. Frozen at Integration Checkpoint A.

| File | Status | What it does |
|---|---|---|
| `schema.sql` | ✅ | The 5 database tables, their columns, indexes and rules. Already applied to the `traffic_trace` database |
| `migrations/001_fix_empty_embedding_check.sql` | ✅ | Closes a hole where an *empty* embedding passed the size check (a NULL CHECK passes). Applied |
| `endpoints.md` | ✅ | Every API URL, what it accepts and returns, the 4 WebSocket events, and the agreed constants (512 dims, 60 km/h, top-20) |
| `README.md` | ✅ | Explains that these files are joint property and lists what is still unconfirmed |

---

## `docs/` — everything for demo day

| File | Status | What it does |
|---|---|---|
| `PITCH.md` | ✅ | 8 slides: content plus the speaker script for each |
| `DEMO_SCRIPT.md` | ✅ | The 7-minute run minute by minute — who says what, the click path, what to say while things load, and the exact fallback sentence |
| `RUNBOOK.md` | ✅ | 14 failure scenarios, each with a 60-second copy-pasteable fix, plus the freeze checklist. **Read the `.env` trap section — gitignored files are not in the backup** |
| `STATS.md` | ✅ | Measured numbers with the command that produced each, and an honest "what these do and do not show" |

---

## `api/` — the backend (Muhammad)

The only code allowed to touch the database or the network.

### Config and setup

| File | Status | What it does |
|---|---|---|
| `README.md` | ✅ | The layered architecture, the dependency rule, and coding conventions. **Give this to Teammate 1** |
| `requirements.txt` | ✅ | List of required Python libraries with exact versions. Like `package.json` |
| `.venv/` | ⚙️ | Where those libraries are installed. Like `node_modules`. Never committed |
| `.env` | ✅ | Real settings incl. the database password. **Never committed** |
| `.env.example` | ✅ | Same file with the password removed, so a teammate knows which settings exist. Committed |

### `app/` — the application

| File | Status | What it does |
|---|---|---|
| `main.py` | ✅ | Assembles the app: settings → CORS → routers. **Wiring only, no logic** |
| `__init__.py` | ✅ | Empty. Tells Python this folder is importable |

### `app/core/` — cross-cutting concerns

| File | Status | What it does |
|---|---|---|
| `config.py` | ✅ | Reads `.env` once into a `settings` object. Nothing else may read `os.environ` |
| `constants.py` | ✅ | The values agreed with Teammate 1: 512 dimensions, 60 km/h, 30 s grace, top-20, 30-minute window. Contract values, **not** tuning knobs |
| `events.py` | ✅ | The live-event bus: a set of connected sockets plus a broadcast function. No broker — one process, nothing to coordinate |
| `security.py` | ✅ | The `X-Officer-Pin` guard. Uses `compare_digest` so a wrong PIN cannot be guessed by timing |

### `app/api/` — the HTTP layer

| File | Status | What it does |
|---|---|---|
| `router.py` | ✅ | Mounts every route module under `/api`. Adding an endpoint means editing only this file plus a new route file |
| `deps.py` | ✅ | `require_camera` — validates the `X-Camera-Token` header. The Express `middleware/` equivalent |

### `app/api/routes/` — one file per resource

Rule: thin. Validate input, call a service, return. **No SQL here.**

| File | Status | What it does |
|---|---|---|
| `health.py` | ✅ | `GET /api/health` — proves the API is alive *and* Postgres is reachable, in one call |
| `cameras.py` | ✅ | Register a camera (token returned once), claim by secret, update GPS location, list. See PROGRESS.md Phase 4 |
| `frames.py` | ✅ | `POST /api/frames` — receives JPEGs, queues them, replies 202 immediately. Plus `GET /api/frames/stats` for queue depth |
| `incidents.py` | ✅ | `GET /api/incidents` (feed) and `GET /api/incidents/{id}` (everything the review screen needs, in one call) |
| `matches.py` | ✅ | `POST /api/matches/{id}/decision` — the officer's confirm/reject. Confirming flips the incident to `confirmed` |
| `journeys.py` | ✅ | `GET /api/journeys/{incident_id}` — 404 until a match is confirmed |
| `ws.py` | ✅ | `WS /ws/live` — pushes `sighting` / `incident` events to the dashboard |
| `admin.py` | ✅ | `verify-pin` and `reset` — both PIN-guarded. Reset wipes data but keeps cameras |

### `app/services/` — business logic

Rule: owns the workflow, knows nothing about HTTP.

| File | Status | What it does |
|---|---|---|
| `geo.py` | ✅ | Distance between cameras and the reachability rule. **Must stay identical to `pipeline.is_reachable`** |
| `matching.py` | ✅ | `rank_by_cosine`, `find_candidates` (gate → rank → hydrate), `run_matching` (→ his scorer → save), `assert_normalized` |
| `pipeline_client.py` | ✅ | **The only file that imports Teammate 1's code.** Stub until Phase 7, plus a field-name alias map so a `bbox`/`box` mismatch errors loudly instead of failing silently |
| `ingest.py` | ✅ | Frame → `process_frame` → save every vehicle as a sighting → open incidents only for violations |
| `evidence.py` | ✅ | Crops to disk named by SHA-256 of contents, so the filename is its own tamper check. Identical crops dedupe automatically |
| `journeys.py` | ✅ | On confirm, calls his `build_journey` and saves the route. Rebuilt on read, never appended |
| `watchlist.py` | ✅ | Runs `check_watchlist` on **every** new sighting — that is how a fled vehicle is spotted again |

### `app/db/` — data access

Rule: **all SQL lives here and nowhere else.**

| File | Status | What it does |
|---|---|---|
| `session.py` | ✅ | Connection **pool**. No other file may call `psycopg.connect`. Pooling saves ~15 ms per query on Windows |
| `numpy_types.py` | ✅ | Reads embeddings from Postgres straight into numpy, skipping Python floats. Worth ~90 ms per match — see PROGRESS.md Phase 3 |
| `queries/cameras.py` | ✅ | Insert, get, get-by-token, list |
| `queries/sightings.py` | ✅ | Insert; **`get_gated_candidates`** — the space-time gate, the hot path of the whole system; plus `get_sightings_by_ids` to hydrate survivors |
| `queries/incidents.py` | ✅ | Insert, get (joined to sighting + camera), list with match counts, set status |
| `queries/matches.py` | ✅ | Save candidates (upsert, never overwrites a decision), record the officer's decision |
| `queries/journeys.py` | ✅ | Save and fetch journeys, with hops in chronological order |

### `scripts/` — one-off operational tools

Run with `python -m scripts.<name>` from `api/`.

| File | Status | What it does |
|---|---|---|
| `seed_cameras.py` | ✅ | Creates the 3 demo cameras, prints their tokens + pairwise distances, and writes `tools/tokens.json` for `replay.py`. Safe to re-run. **Coordinates are placeholders** |
| `bench_matching.py` | ✅ | The Phase 3 acceptance test: proves matching stays under 50 ms. Cleans up after itself |
| `preflight.py` | ✅ | "Is this machine ready to demo?" — checks Python, every import, all 7 pipeline functions being real, the DB, weights, tiles, disk. Run it the night before |
| `smoke_demo.py` | ✅ | End-to-end smoke test — 52 checks driving the real API: auth, ingest, ranking, confirm, journey, WebSocket, error paths. **Destructive** (resets twice), leaves the DB clean. Run it before the phones are set up |
| `test_case_grouping.py` | ✅ | Six scenarios for when a violation opens a NEW case and when the officer's confirm folds two into one. The most intricate rule in the product. **Destructive**, leaves the DB clean |
| `bench_matcher.py` | ✅ | Measures the **fused** score on the production path — real stored embeddings, the same `build_scoring_payload` the API uses, then `pipeline.score_candidates`. `labelset/benchmark.py` scores one embedding function and cannot see a weight change or an attribute filter; this can. A candidate the scorer drops entirely is scored 0.0 and flagged, so a hard filter that deletes a true match shows up instead of hiding. Read-only |
| `export_labelset.py` | ✅ | Exports the officer's labels and the crops they were made on as `labelset/` — a folder that runs on a machine with no database, no API and no crops. Read-only. Re-run after every labelling session; more labels are strictly better |
| `labelset_kit/` | ✅ | The two files copied into every export: `benchmark.py` (standalone; the only thing anyone edits is `build_embedder()`) and its `README.md`. Reports margin, rank-1 and ms/crop, with the shipped fused score printed alongside for comparison |
| `test_burst_dedupe.py` | ✅ | One vehicle passing one camera once must be ONE candidate, not three. Pure function, no DB, no server. Also asserts the clearest frame is the one kept, and that three separate bikes stay three |
| `test_same_camera_fix.py` | ✅ | Regression test for the same-camera scoring exploit. Now asserts it is closed on **both** sides — our gate excludes same-camera rows, and `_space_time_score` no longer rewards them |
| `bench_embeddings.py` | ✅ | Measures same-vehicle vs different-vehicle separation, raw and fused |
| `test_numpy_loader.py` | ✅ | Proves the fast embedding reader is byte-exact. A silent misread would corrupt matching |
| `seed_matches.py` | ✅ | Test-only: fills candidate matches so the review screen has something to show before Phase 11 |
| `download_tiles.py` | ✅ | Caches OSM map tiles for offline use. **Needs internet — run before demo day** |

### `app/schemas/` — request/response shapes

| File | Status | What it does |
|---|---|---|
| `cameras.py` | ✅ | Camera request/response models with range validation (lat −90..90 etc.) |
| *(others)* | 🔜 Phase 5+ | Pydantic models. Like Zod/Joi, but they also generate the `/docs` page automatically |

### `app/workers/` — background jobs

| File | Status | What it does |
|---|---|---|
| `frame_worker.py` | ✅ | Drains the frame queue. Separate so `POST /api/frames` answers instantly — a phone waiting on AI would drop frames. Bounded queue: under overload it drops frames rather than memory |
| `retention.py` | ✅ | Hourly sweep deleting unlinked sightings after 48h. The privacy promise in the pitch, actually running |

---

## `dashboard/` — the officer's screen (Muhammad)

| File | Status | What it does |
|---|---|---|
| `package.json` | ⚙️ | Node dependencies and the `npm run dev` script |
| `src/app/layout.tsx` | ⚙️ | The shell wrapping every page |
| `src/app/page.tsx` | ✅ | Live event monitor. Phase 9 turns this into the real incident feed |
| `src/app/globals.css` | ⚙️ | Tailwind + the shadcn theme colours |
| `src/components/ui/button.tsx` | ✅ | A shadcn component. shadcn **copies source into your project**, so you can edit it |
| `src/lib/utils.ts` | ✅ | The `cn()` helper for merging Tailwind classes |
| `components.json` | ✅ | shadcn's config — where to put new components |
| `next.config.ts`, `tsconfig.json`, `eslint.config.mjs`, `postcss.config.mjs` | ⚙️ | Build, TypeScript, linting and CSS config |
| `public/*.svg` | ⚙️ | Default Next.js images. Deletable |
| `AGENTS.md`, `CLAUDE.md` | ⚙️ | Auto-created by `create-next-app`. Harmless |

**Planned:**

| Path | Phase | What it will do |
|---|---|---|
| `src/app/camera/page.tsx` | ✅ 6 | The phone page: claim by secret → GPS → capture loop with motion burst, wake lock, retry/backoff, live status |
| `src/lib/config.ts` | ✅ 6 | Works out the API address from the browser's own hostname, so phones on the hotspot reach the laptop |
| `src/lib/motion.ts` | ✅ 6 | Detects movement on a 32×24 thumbnail to decide when to burst to 4 fps |
| `src/hooks/useWakeLock.ts` | ✅ 6 | Stops the phone screen sleeping and killing the capture loop |
| `src/app/incidents/page.tsx` | ✅ 9 | The feed. New incidents render straight from the live event |
| `src/app/incidents/[id]/page.tsx` | ✅ 10 | Review screen: evidence, candidates, score bars, confirm/reject, keyboard shortcuts |
| `src/components/Shell.tsx` | ✅ 9 | Sidebar + live-connection dot |
| `src/components/PlateBadge.tsx` | ✅ 9 | The "UNREADABLE · fingerprint mode" badge — the product's headline |
| `src/app/map/page.tsx` | ✅ 12 | Live map page (loads Leaflet with `ssr:false`) |
| `src/components/LiveMap.tsx` | ✅ 12 | Leaflet map: camera markers (green live / grey silent / pulse), incident markers, offline tiles |
| `src/components/OfficerGate.tsx` | ✅ 16 | PIN keypad + "Reset demo" button in the sidebar |
| `src/app/incidents/[id]/report/page.tsx` | ✅ 15 | Court-style case file. Print-to-PDF, SHA-256 beside every image |
| `src/app/journeys/page.tsx` | ✅ 13 | Incident picker + the animated route — the demo money-shot |
| `src/components/JourneyMap.tsx` | ✅ 13 | Route drawn hop by hop, thumbnails and per-hop confidence |
| `src/components/AlertToasts.tsx` | ✅ 14 | "Possible reappearance" toast, shown on every page |
| `src/lib/api.ts` | 9 | One place that calls the backend |
| `src/lib/ws.ts` | ✅ 8 | WebSocket client with auto-reconnect and backoff |
| `public/tiles/` | ✅ 12 | 528 cached OSM tiles (3.5 MB). Gitignored. Re-run `download_tiles.py` if the demo area changes |

---

## `pipeline/` — the AI (👤 Teammate 1)

Pure functions. **No database, no HTTP.** The API imports these; they never import from the API.

| File | Status | What it does |
|---|---|---|
| `README.md` | ✅ | His brief: which functions to provide, and the constraints that changed |
| `__init__.py` | ✅ 👤 | Exposes the seven functions. **All seven are real** as of pipeline_v9. `is_reachable` now applies the 30 s grace |
| `types.py` | ✅ 👤 | Dataclasses + `EMBEDDING_DIM = 512` |
| `orchestrator.py` | ✅ 👤 | `process_frame` — detection + helmet + fingerprint. v9: **never raises**, and fingerprints the whole frame in one batched CLIP call |
| `detector.py` | ✅ 👤 | YOLOv8n. Finds vehicles and attaches riders to motorcycles |
| `helmet.py` | ✅ 👤 | His custom-trained helmet model. v9 returns `{status, confidence}`, not a bare string — `orchestrator.py` was updated with it |
| `fingerprint.py` | ✅ 👤 | CLIP ViT-B/32 → 512-dim L2-normalized embedding + colour histogram. v9 adds `fingerprint_batch` and the `passenger_count` / `helmet_color` attrs |
| `requirements.txt` | ✅ | Written from his venv — he had none. CPU torch builds |
| `yolov8n.pt`, `helmet_model.pt` | ✅ 👤 | Model weights (12 MB). Gitignored |

| `matcher.py` | ✅ 👤 | `score_candidates` — fuses 4 signals. CLIP weighted lowest (0.20) on purpose. v9: `distance_m == 0` now scores **None** (missing), which is the root fix for the same-camera exploit |
| `journey.py` | ✅ 👤 | `build_journey` — orders stops, per-hop distance/time/confidence |
| `alpr.py` | ✅ 👤 | `read_plate` via fast_alpr. **Imported at module load — a missing lib breaks the whole pipeline** |
| `check_watchlist` | ✅ 👤 | In `matcher.py`, reuses `score_candidates`, threshold `WATCHLIST_ALERT_THRESHOLD` |
| `dedupe.py` | ✅ 👤 | Union-find burst dedup: same camera, within 3 s, cosine ≥ 0.95 → keep the highest-confidence one. Wired into `ingest_frame` |
| `selftest.py` | ✅ 👤 | Contract check — run before sending a folder over. 13 checks, all passing |
| `smoke.py` | ✅ 👤 | His quick end-to-end smoke run |

---

## `tools/` — 👤 Teammate 1

| File | Status | What it does |
|---|---|---|
| `README.md` | ✅ | Explains replay.py's role |
| `replay.py` | ✅ 👤 | Feeds recorded frames into the API pretending to be a live phone, one thread per camera, original timing preserved. **The demo-day safety net.** Verified live end to end |
| `test_recordings/cam-A/` | ✅ 👤 | 3 sample frames + `manifest.json` — enough to smoke-test replay without a real recording |
| `tokens.json` | ✅ | Camera secrets keyed `cam-A/B/C`, written by `scripts/seed_cameras.py`. **Gitignored** |

---

## `evidence/` — runtime data

| File | Status | What it does |
|---|---|---|
| `.gitkeep` | ✅ | Empty file that keeps the folder in git while its contents stay out |
| `<sha256>.jpg` | 🔜 Phase 5 | Cropped vehicle photos. Filename **is** the file's SHA-256 hash, so any tampering is detectable — that is what makes the case file court-credible |
