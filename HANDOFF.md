# Traffic_Trace — start here

**Written 31 Aug 2026.** This is the *current state*. `PROGRESS.md` is the full
history, ~1900 lines, appended once per phase; read it only when you need the
reasoning behind something here.

Reply in simple Roman Urdu when Daniyal writes in Roman Urdu. Explain FastAPI by
mapping to Express — he is a MERN developer.

---

## 1. What this is

Traffic violation detection where **the number plate cannot be read**.

It is a **feature upgrade to an existing ANPR deployment, not a replacement**.
That sentence decides the architecture:

- Plate readable → record the incident, mark it ANPR-handled, **do no matching**.
- Plate unreadable → this feature takes over: fingerprint the vehicle, find it at
  other cameras, let an officer confirm, draw the route.

Only `no_helmet` is detected, so **only motorcycles are tracked** — no car, bus or
truck can commit it, and including them cost 71% of frame time and 16 of 20
candidate slots.

---

## 2. Running it

```powershell
cd "d:\Daniyal Files\Traffic_Trace"
.\start_demo.ps1
```

Starts Postgres, writes `tools/tokens.json`, launches API + dashboard in their own
windows, prints the LAN IP, the three camera tokens and the officer PIN. Two
windows must stay open.

| | |
|---|---|
| API | `http://localhost:8000` · docs at `/docs` |
| Dashboard | `http://localhost:3000` — incidents / map / journeys / camera |
| Phones | `http://<lan-ip>:3000/camera` |
| Officer PIN | `4321` |
| Python | `api\.venv\Scripts\python.exe` — **3.12 only** |
| Database | native PostgreSQL 18, service `postgresql-x64-18`, db `traffic_trace` |

**Never `npm run dev`** for the dashboard — the phone renders the page and never
hydrates, so every button silently does nothing. Production build only.

Phones need `chrome://flags` → `unsafely-treat-insecure-origin-as-secure` →
`http://<lan-ip>:3000` → **Relaunch** (force-stop Chrome on ColorOS). Without it
`navigator.mediaDevices` is undefined and the camera never starts.

### First end-to-end run on real footage (31 Aug)

Video played to camera 1, then camera 2. Not a synthetic test — this is the whole
product working once, on real street footage, and it is the reference to compare
future runs against:

```
9 sightings  ->  4 real passes  ->  3 candidates offered  ->  officer picked the right one
incident   Camera 1  01:53:35   plate unreadable, fingerprint mode
confirmed  Camera 2  01:54:05   score 0.754
journey    2 stops, 0.896 km, 29.9 s
```

Camera 3 was never set up for this run, so the three-stop journey is still untested.

### Tests

```powershell
cd api
.\.venv\Scripts\python.exe -m scripts.preflight          # is this machine ready
.\.venv\Scripts\python.exe -m scripts.smoke_demo         # 52 checks, whole flow
.\.venv\Scripts\python.exe -m scripts.test_case_grouping # 6 scenarios, case rules
.\.venv\Scripts\python.exe -m scripts.test_same_camera_fix
.\.venv\Scripts\python.exe -m pipeline.selftest          # from the repo root
```

`smoke_demo` and `test_case_grouping` are **destructive** — they reset the demo
data twice and leave it clean. Run them before the phones are set up, never
during.

---

## 3. 🔴 Open right now

| # | Thing | Notes |
|---|---|---|
| 1 | ~~`GATE_MAX_REQUIRED_GAP_SECONDS`~~ **done 31 Aug — now `None`, preflight passes.** What replaces it: **a filming rule** | The real gate demands **≥ 24 s before camera 2** and **≥ 2 min before camera 3**. Show the video faster than that and the true match is rejected before it is ever scored — empty review screen. Measured: the one confirmed match was a 30 s hop, through by 6 seconds |
| 2 | Work is uncommitted, **and that is deliberate** | Daniyal is not committing yet. Do not run git, do not offer commit commands, do not raise it — he will ask when he wants it |
| 3 | **Ranking is wrong, and no threshold fixes it** | 31 Aug run, labelled: the true match scored 0.754 *between* two different bikes at 0.856 and 0.719. See §4. Needs labelled runs and a weight change, not a threshold change |
| 4 | Camera positions have **drifted from the seed** | Phones reported their own GPS. Now 0.92 / 2.23 / 2.43 km apart, not the seeded 1.37 / 1.62 / 2.10. Re-run `scripts.seed_cameras` to reset (it also rewrites `tools/tokens.json`) |
| 5 | Camera coordinates are still **Karachi placeholders** | Change them, then re-run `scripts.download_tiles` **while there is internet** |
| 6 | No real recordings for the replay fallback | `tools/recordings/` needs a `cam-A`, `cam-B` and `cam-C` folder, each with a `manifest.json`. Only sample frames exist |
| 7 | One phone's Chrome flag never worked | `navigator.mediaDevices` undefined. Compare its `chrome://flags` entry against a working phone |
| 8 | No rehearsal has happened (Phase 19) | The only phase left |
| 9 | The incident keeps the **first** flagged frame, not the clearest | A later frame often has higher confidence and would make a better card. Candidates already pick the clearest (`collapse_bursts`); ingest still does not — Camera 1 kept conf 0.48 when 0.58 was available |
| 10 | Weight tuning on real street data | Teammate 1's Phase 11, still hand-set |

---

## 4. Measurements that must not be re-derived

Every one of these was expensive. **Do not "improve" the things they explain
without new measurements of your own.**

### Ingest latency — why the queue is 8, not 64

Queue depth *is* a latency budget: a frame waits `depth / throughput`. At ~1.2
frames/s, 64 was a **54-second** buffer, and a violation frame posted into a busy
queue was evicted by newer arrivals before it was ever processed — **the incident
never appeared at all**.

```
QUEUE_MAXSIZE = 64  ->  incident visible after 19.3s (or never, under load)
QUEUE_MAXSIZE = 8   ->  incident visible after  5.1s
```

Three phones ask ~2.5× what this CPU can process. A high `dropped` with low
latency is the system working correctly.

### Space-time is a GATE, not an identity signal

`build_scoring_payload` deliberately **does not send** `distance_m` /
`time_gap_seconds`. On real labelled footage it was *inverted* — it rewarded
vehicles that dawdled:

| Signal | Confirmed same rider | Different bike |
|---|---|---|
| vehicle (CLIP) | 0.90 – 0.94 | 0.85 – 0.90 |
| rider (CLIP) | 0.87 – 0.95 | 0.83 – 0.92 |
| **colour** | **0.54 – 0.67** | **0.35** |
| **time + distance** | **0.51 – 0.52** | **0.79** ← wrong way round |
| fused, before | 0.660 – 0.712 | 0.687 – 0.692 (overlapping) |
| **fused, after** | **0.741 – 0.817** | **0.632 – 0.638** (+0.103 apart) |

`score_candidates` treats a missing distance as a missing signal and
redistributes its weight, so no change to `pipeline/matcher.py` was needed.
`services/watchlist.py` uses `is_reachable` as a *filter* for the same reason.

`MIN_CANDIDATE_SCORE = 0.70` lives in that gap.

### One pass at one camera was becoming three candidates

31 Aug run: **9 sightings, 4 real vehicle passes.** A camera sampling ~1 fps sees
the same bike in two or three consecutive frames, and each frame became its own
card — the officer was asked the same question twice about the same photograph.
Six candidates on one incident were really three bikes.

Grouping had to be on **time**, because similarity cannot do it:

| | gap | veh cosine |
|---|---|---|
| same pass, same camera | 1 – 2 s | 0.850 – 0.943 |
| different bike, same camera | 120 – 346 s | 0.691 – 0.889 |

The cosines **overlap**; the time gaps are two orders of magnitude apart.
`pipeline/dedupe.py`'s 0.95 would have collapsed nothing, and any value low
enough to work would merge different riders. `services/matching.collapse_bursts`
groups on time alone and keeps the highest-confidence frame of each burst.

A tracker (SORT/ByteTrack) is the textbook answer and does not apply here: at
~1.2 fps with drops there is no frame-to-frame continuity to associate.

### No threshold separates a true match from a false one

First candidate labelled by Daniyal on real footage, 31 Aug, after burst dedupe:

```
0.856  different bike   rider 0.818  vehicle 0.864  colour 0.870
0.754  THE SAME BIKE    rider 0.862  vehicle 0.851  colour 0.636
0.719  different bike   rider 0.805  vehicle 0.826  colour 0.605
```

The true match sits **between** two false ones. `MIN_CANDIDATE_SCORE` cannot be
tuned out of this — above 0.754 it discards the real vehicle. The 30 Aug gap
(0.741–0.817 vs 0.632–0.638) did not hold on a second run.

What the run does hint: `rider` ranked the true match first, `colour` lifted a
different bike above it. That is a **weight** question, and one labelled example
is not enough to act on. Every officer decision stores a label in
`matches.decision` — collect several runs before touching a weight.

### The ranking is right. The threshold was the wrong instrument.

1 Sep, 24 labelled cross-camera pairs across three incidents — the largest
labelled set so far, and the first that says something useful:

```
rank-1     3/3      the confirmed match ranked FIRST in every incident
margin    -0.077    confirmed 0.853-0.951   rejected 0.730-0.930   overlapping
```

Both things are true at once, and that is the whole point: **the order is
trustworthy, the absolute number is not.** Every one of the 21 stored candidates
cleared `MIN_CANDIDATE_SCORE = 0.70`, so the review screen showed all ten and the
officer was handed the entire album — the thing this product exists to avoid.

The cause is CLIP's range: any two motorcycles score 0.73-0.96, so an absolute cut
on that score can only be all or nothing. Reverting the weights does not fix it
either — measured on the same run, the old weights hide 5 of 21 and still show 16.

So the cut moved to where ranking can be used: the screen asks about the top
`SHORTLIST` and offers the rest behind one click. Nothing is deleted, and a wrong
ranking costs a click rather than the vehicle. Top-5 held 6 of the 7 confirmed
matches; top-1 was correct in all three incidents.

Removing that threshold also fixed `smoke_demo`, which had been failing two checks
because its candidates scored 0.61 and were hidden.

### The phone was uploading sideways pictures

1 Sep. Landscape is the right way to hold the phone — a landscape monitor filmed
in portrait wastes half the frame and leaves the bike under the size floor. But in
landscape, detection went to **zero**, and it took looking at a saved frame to see
why: `getUserMedia` hands back frames in the **sensor's** orientation. The browser
rotates the `<video>` element for display, so the phone looks perfectly correct
while `drawImage` copies the raw, sideways frame onto the canvas. A motorcycle
lying on its side is not a motorcycle to a detector trained on upright images.

Measured on one real landscape capture:

```
as uploaded              0 motorcycles
rotated 90° clockwise    0
rotated 90° COUNTER-cw   2 motorcycles, 122 px and 169 px   <- both over the floor
rotated 180°             0
```

`captureOnce` now rotates by `-screen.orientation.angle`, which covers both
landscape directions. Two things came out of the same session:

- A dead stream still reports `readyState >= 2` and still draws — it draws black.
  147 frames were uploaded as 10,388-byte pure-black JPEGs while the phone looked
  healthy. There is now a blank-frame guard (brightest pixel < 8 → do not send,
  say so on screen, re-acquire the stream) and a restart on
  `orientationchange` / `visibilitychange`.
- **A count is not a check.** "0 detected" was logged hundreds of times and could
  not distinguish an empty road from a black frame from a sideways one. Saving one
  sample frame and looking at it answered it in a minute. `logs/frames/` keeps one
  per camera per 15 s, only when nothing was detected.

### Vision cannot tell two motorcycles apart

Across four frames of **one** bike at **one** camera:

```
CLIP cosine       0.865 - 0.932
colour overlap    0.32  - 0.78
colour name       gray -> blue -> gray
```

All inside the range two *different* bikes produce. **Any threshold that claims to
say "same vehicle" from pixels is false confidence.** This was learned three times
in one day; see §5.

### Same-camera pairs score a free 1.0

`distance_m == 0` used to give a perfect space-time score, so an unrelated bike at
the same camera outranked the true cross-camera match. Fixed upstream (returns
`None`) **and** in `services/geo.py` / `services/watchlist.py`, which exclude
same-camera pairs. Both layers are kept on purpose — the demo does not depend on
an upstream file continuing to behave.

### Map tiles

OSM answers **HTTP 200 with an "Access blocked" image** for bulk downloads. Carto
stamps **"API KEY REQUIRED"** across every tile without a key. Both passed every
automated check. Tiles now come from `tile.openstreetmap.de`.

**A count is not a check, and neither is a hash.** The only sufficient check is
rendering the image and looking at it.

---

## 5. The rules, and the reasoning behind each

### One rider, one offence, one card

```
several frames of one pass at one camera   -> ONE case (time-based, 30s window)
the same rider at other cameras            -> a case each, at first
the officer confirms "same vehicle"        -> the duplicate folds away
a different rider                          -> always its own case
```

Merging is driven **only by the officer's confirm** (`incidents.merged_into`).

**Automatic grouping from a score was tried and abandoned — twice.** First on any
watchlist hit (≥0.6): it swallowed six genuinely different helmetless riders, each
filed as the bike already on record and never investigated. Then at a higher
threshold (0.85), justified by a measurement of "the same bike" scoring 0.9158 —
which had been taken by posting the *identical image* at both cameras. Real crops
of one bike from two cameras score **0.52 – 0.55**, lower than different bikes
score. There is no threshold. Only the officer knows.

The within-camera merge is still time-based (`INCIDENT_MERGE_WINDOW_SECONDS = 30`)
and marked `ponytail:` with its ceiling: two different offenders at one camera
inside 30 s become one case.

### Tuned constants

| Constant | Value | Where | Why |
|---|---|---|---|
| `QUEUE_MAXSIZE` | 8 | `workers/frame_worker.py` | latency, see §4 |
| `MIN_VEHICLE_HEIGHT_PX` | 96 | `services/ingest.py` | below this a crop is upscaled mush. Measured: too far 60–71 px, usable 145–214 px |
| `INCIDENT_MERGE_WINDOW_SECONDS` | 30 | `services/ingest.py` | one pass = one case |
| `BURST_WINDOW_SECONDS` | 5 | `core/constants.py` | one pass = one candidate, see §4 |
| ~~`MIN_CANDIDATE_SCORE`~~ | **retired 1 Sep** | — | measured useless: 21 of 21 candidates cleared it. Replaced by `SHORTLIST` |
| `SHORTLIST` | 5 | `dashboard/.../incidents/[id]/page.tsx` | cut by rank, not score, and soft — see §4 |
| `GATE_MAX_REQUIRED_GAP_SECONDS` | **2.0 ← temporary** | `core/constants.py` | bench testing. **Set to `None` before demo** |
| `BURST_INTERVAL_MS` | 1000 | `dashboard/.../camera/page.tsx` | 3 phones at 250 ms asked 12 fps of a 1 fps machine |

### Evidence crops include the rider

YOLO's motorcycle box stops below the person. Most commuter bikes look identical;
the rider is what an officer recognises. `save_crop(..., also=rider_bboxes)` crops
the union — measured 1.49–1.81× taller.

---

## 6. Architecture, briefly

```
dashboard/   Next.js 16, its own git repo (Traffic-Trace-Frontend)
api/         FastAPI — routes/ -> services/ -> db/queries/, one direction only
pipeline/    Teammate 1's AI. Pure functions, no DB, no HTTP
tools/       replay.py — the demo fallback if phones fail
contracts/   schema.sql + endpoints.md, the frozen interface
```

- `api/` imports `pipeline/`. `pipeline/` must never import from `api/`.
- **`services/pipeline_client.py` is the only file that imports `pipeline/`.**
- A route containing SQL is a bug. A service importing `fastapi` is a bug.
- Embeddings are `float4[]` + numpy cosine, **not pgvector**. SQL gates by
  space-time, numpy ranks by cosine.
- Docker / WSL2 / Hyper-V are **permanently impossible** on this laptop.

### Two things that bite

- `tools/tokens.json` is written by both `seed_cameras.py` and `start_demo.ps1`.
  Both must `ORDER BY name` — `created_at` order on this machine is *reversed*,
  and `cam-A` silently meaning Camera 3 sends replay frames as the wrong camera.
- PowerShell's `Out-File -Encoding utf8` writes a **BOM** that `json.load` rejects.
  Readers use `utf-8-sig`; the writer uses `UTF8Encoding($false)`.

---

## 7. Working agreements

- **Daniyal owns all git operations.** Never run `git` or `gh` — give him commands
  to paste.
- Update `PROGRESS.md` and `FILES.md` at the end of every phase, unasked.
- Measure before changing a threshold. Three wrong turns in one day all came from
  measurements taken on synthetic inputs — identical images, random vectors —
  which cannot reveal a signal that is inverted on real ones.
- When a test fails, check the test first. Twice the code was right and the test's
  wait helper returned before the worker had finished. Wait on an exact
  `processed` count, never on "the queue looks quiet".
