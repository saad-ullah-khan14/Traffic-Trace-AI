# Traffic_Trace — Failure Runbook & Freeze Checklist

> **What this is.** Every way this demo can break, with the exact command or tap that fixes
> it. Written to be executed by someone whose hands are shaking while three judges watch.
>
> **How to use it.** Find the symptom in the triage table, jump to that section. Each section
> is: what you see → what you do → what you say out loud while doing it. Nothing here takes
> longer than 60 seconds.
>
> **Print this.** One paper copy in the bag. If the laptop is the thing that died, a runbook
> on the laptop is not a runbook.
>
> Companion documents: `docs/DEMO_SCRIPT.md` (the 7-minute script and the pre-stage
> checklist) · `PROGRESS.md` §0 (credentials, run commands) · `start_demo.ps1` (the launcher,
> which already refuses to say "ready" for most of the failures below).

---

## Who to call for what

| It broke in | Owner | Examples |
|---|---|---|
| `api/`, `dashboard/`, Postgres, the hotspot, the phones, the laptop | **Daniyal** | API won't start, blank map, no journey, PIN, reset, tokens, build, network |
| `pipeline/` — anything AI | **Saad** | `pipeline.real == false`, nothing detected, helmet missed, bad candidate scores, slow inference, `tools/replay.py` |

**The dividing line:** if the fix is a command in `api/`, `dashboard/` or PowerShell, it is
Daniyal's. If the fix is inside `pipeline/*.py`, it is Saad's — **and nobody edits Saad's
files during a demo.** Mid-demo the answer to a pipeline bug is always the fallback (§14),
never a code change.

**During the 7 minutes, one person fixes and one person talks.** Never both fix. The audience
will forgive a pause; it will not forgive two silent people staring at a laptop.

---

## 10-second triage

| What you see | Go to |
|---|---|
| Phone dead / screen black / page frozen | [§1](#1-phone-dies-or-will-not-stream) |
| Red **● JS NOT running** on the camera page | [§2](#2-red-js-not-running-banner) |
| Phone can't load the page at all | [§3](#3-phone-cannot-reach-the-laptop) |
| "Camera unavailable" / "GPS failed" on the phone | [§4](#4-camera-or-gps-permission-denied) |
| API window shows a traceback / never answers | [§5](#5-api-will-not-start) |
| `/api/health` → `"pipeline": {"real": false}` | [§6](#6-pipelinereal--false--the-ai-is-not-running) |
| DB errors everywhere, `db.ok: false` | [§7](#7-postgres-is-not-running) |
| Feed full of yesterday's junk | [§8](#8-database-has-junk-from-testing) |
| Incident opens, candidate list empty | [§9](#9-no-candidates-for-an-incident) |
| Reappearance ride produced no toast | [§9.5](#95-the-reappearance-never-alerted--because-the-incident-was-already-confirmed) |
| Everything lags, `dropped` climbing | [§10](#10-matching-or-ingest-is-slow) |
| Map is grey squares | [§11](#11-map-is-blank) |
| `/journeys` says nothing to show | [§12](#12-journey-does-not-appear) |
| Laptop dead / won't boot | [§13](#13-laptop-dies) |
| It is just going badly | [§14](#14-live-demo-is-going-badly--switch-to-replay) |

---

## 1. Phone dies or will not stream

**Symptom.** Handset is dead, screen frozen, Chrome crashed, or the camera preview stopped
and the counters are stuck.

**Key fact, and say it out loud:** *a token identifies a camera, not a handset.* Any phone
that claims the same token **becomes** that camera. There is no re-registration, no server
change, nothing to restart.

### Fastest fix first (5 seconds)

On the phone, in this order — stop at the first that works:

1. **Stop** → **Start streaming**.
2. Reload the page. The token is in `localStorage` (`traffic_trace.camera_token`), so it does
   **not** ask for the secret again.
3. Swap to the spare handset.

### Swapping to the spare handset (30 seconds)

The spare must already be prepared (see the freeze checklist, §F4). If it is:

1. Open `http://<LAPTOP_IP>:3000/camera` on the spare.
2. Confirm the header shows green **● JS ready**. If it is red, go to
   [§2](#2-red-js-not-running-banner).
3. Paste that camera's token → **Claim this camera**.
4. **Use my GPS location** → **Save position and continue**. If the GPS is slow or wrong, type
   the coordinates by hand — they are on the printed token card.
5. **Start streaming.** Put it on the tripod.

**If you do not have the token to hand,** on the laptop:

```powershell
$env:PGPASSWORD='trafficdev'; psql -U postgres -d traffic_trace -c "SELECT name, token FROM cameras ORDER BY name;"
```

**Say while doing it:** *"Saad is swapping the handset. The camera identity lives in the
token, not the phone — the new one just picks up as the same camera. Nothing on the server
changes."*

**If the phone is fine but the counters freeze after a minute or two:** the wake lock was
dropped when the tab was backgrounded. Bring Chrome to the foreground and tap the page once.
Battery saver is the usual cause — it must be **off** (see §F4).

---

## 2. Red "JS NOT running" banner

**Symptom.** The camera page renders perfectly, the header says
**● JS NOT running — enable JavaScript in Chrome settings**, and every button silently does
nothing. The secret field clears itself on reload.

**This is almost never JavaScript being disabled. It is the dev-build trap.**

`npm run dev` ships about **4 MB** of JavaScript (React devtools, HMR client, unminified
chunks). Over a phone hotspot it never finishes downloading, so the page **renders but never
hydrates**. The production build is **563 KB** and loads fine. This cost us a whole debugging
session in Phase 6 — it reads exactly like a broken app.

### The fix (40 seconds, on the laptop)

Look at the dashboard window's title bar and its first line of output. If it says `next dev`,
**Turbopack**, or a `Local:` / `Network:` pair, you are on the dev build. Kill that window and
run the production build:

```powershell
cd "d:\Daniyal Files\Traffic_Trace\dashboard"
npm run build
npm run start -- -H 0.0.0.0 -p 3000
```

Then **hard-reload on the phone**: Chrome ⋮ → reload. If it is still red, close the tab and
reopen the URL.

> **The rule:** `npm run dev` is for the laptop only, and only when no phone is involved.
> `start_demo.ps1` always uses the production build — if you started with the script, you are
> not on dev, and the real cause is [§3](#3-phone-cannot-reach-the-laptop) (the JavaScript is
> simply not arriving over the network).

**Also possible, much rarer:** the phone genuinely has JS disabled —
`chrome://settings/content/javascript` → Allowed. Check this only after ruling out the build.

---

## 3. Phone cannot reach the laptop

**Symptom.** `ERR_CONNECTION_REFUSED`, `ERR_ADDRESS_UNREACHABLE`, or the page just spins. Or
the page loads but claiming fails, frames 401, and nothing uploads.

**Cause, 9 times out of 10: the hotspot handed out a different IP than the one in the Chrome
flag.** The flag is matched as an exact string, including the port.

### Step 1 — get the laptop's current IP (5 seconds)

```powershell
(Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' } | Select-Object -First 1).IPv4Address.IPAddress
```

Or the blunt version: `ipconfig | findstr /i "IPv4"`.

`start_demo.ps1` prints this same address under **LAPTOP IP** when it finishes. If the address
is not the one the phones have, everything below follows.

### Step 2 — fix the Chrome flag on each phone (30 seconds per phone)

`chrome://flags` → search **unsafely-treat-insecure-origin-as-secure** → into the text box put
the **exact** origin:

```
http://10.249.50.6:3000
```

replacing the IP with the one from step 1. Set the dropdown to **Enabled**. Tap **Relaunch**.

**Exact means exact.** All of these are wrong and all of them fail silently:

| Wrong | Why |
|---|---|
| `https://10.249.50.6:3000` | wrong scheme |
| `http://10.249.50.6` | missing `:3000` |
| `http://10.249.50.6:3000/` | trailing slash |
| `http://10.249.50.6:8000` | that is the API port, not the page origin |
| yesterday's IP | the hotspot re-leased |

The flag accepts a comma-separated list. **Put every IP the hotspot has ever handed you into
it, comma-separated** — then a re-lease does not matter:

```
http://10.249.50.6:3000,http://192.168.43.1:3000,http://172.20.10.2:3000
```

Do this the night before. It is the single cheapest insurance in this document.

> **What the flag actually gates:** Chrome treats `http://` origins as insecure and blocks
> `getUserMedia` **and** `geolocation` on them. Without the flag the page loads, the buttons
> work, and both the camera and the GPS fail. That is why a wrong flag looks like a broken app
> rather than a permission problem.

### Step 3 — if the IP is right and it still will not connect

- **Is the laptop actually on the hotspot?** Windows silently prefers a remembered WiFi. Check
  the network icon; reconnect to the phone hotspot.
- **Windows Firewall** blocking node/python on a newly-seen network profile. When Windows
  asks, it must be allowed on **Private**. If it was denied once: Windows Security → Firewall
  & network protection → Allow an app → tick **Private** for `node.exe` and `python.exe`.
- **Test from the laptop first:**
  `curl.exe -s -o NUL -w "%{http_code}" http://127.0.0.1:3000/camera`
  If that is not `200`, the problem is the server, not the network — go to
  [§5](#5-api-will-not-start).
- **Then test the laptop's own LAN address, from the laptop:**
  `curl.exe -s -o NUL -w "%{http_code}" http://<LAPTOP_IP>:3000/camera`
  `200` means the server is listening on the network correctly and the problem is phone-side.
- **Servers not bound to `0.0.0.0`.** Both must be: `-H 0.0.0.0` for the dashboard,
  `--host 0.0.0.0` for uvicorn. Bound to `127.0.0.1` they work perfectly on the laptop and are
  invisible to every phone.

**Say while doing it:** *"The hotspot re-issued the laptop's address, so the phones are being
pointed at the new one. The system itself is untouched."*

---

## 4. Camera or GPS permission denied

**Symptom.** The phone shows `Camera unavailable: <reason>. On http the Chrome
insecure-origin flag must include this exact address.` Or
`GPS failed (<reason>). Enter the position manually — the seeded value is already filled in.`

**First: check the flag.** Both failures share the same most-likely cause —
[§3, step 2](#step-2--fix-the-chrome-flag-on-each-phone-30-seconds-per-phone). The flag gates
**both** APIs. Rule that out before touching anything else.

### If the flag is definitely correct

**Camera:** Chrome ⋮ → **ⓘ / Site settings** → **Camera** → **Allow** → reload.
If it was permanently blocked earlier: `chrome://settings/content/camera` → find the origin
under Blocked → remove it → reload.
If another app holds the camera (WhatsApp, the stock Camera app, a video call), close it —
Android hands the camera to one app at a time.

**GPS — do not fight it. Use the fallback; it is a designed feature, not a workaround.**
On the locate step, type the surveyed coordinates into the **Latitude / Longitude** boxes and
tap **Save position and continue**. The coordinates are on the printed token card.

The page rejects blank fields, non-numbers, out-of-range values and exactly `(0, 0)`, so a
fat-fingered entry cannot silently park the camera in the Atlantic. It **cannot** catch a
plausible-but-wrong number, and camera position feeds the reachability gate — a camera in the
wrong place produces zero candidates forever. **Read the numbers back before saving.**

**Say while doing it:** *"GPS indoors is unreliable, so a surveyed position can be typed in by
hand. In a real deployment these are fixed poles with surveyed coordinates anyway, not phones
guessing."*

---

## 5. API will not start

**Symptom.** The `Traffic_Trace API :8000` window shows a traceback and closes, or
`start_demo.ps1` says *"the API never answered … within 120s"*, or
`curl.exe -s http://127.0.0.1:8000/api/health` returns nothing.

**Read the API window — the traceback is in it and it names the cause.** Then check the four
causes below **in this order**. This is the order of how often each actually happens.

### 5.1 Port 8000 already taken by an older run (most common)

Traceback contains `[Errno 10048]` or *"only one usage of each socket address"*.

**Diagnose:**
```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen | Select-Object OwningProcess
```

**Fix — kill whatever holds it:**
```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

Then re-run `start_demo.ps1`. Same command with `3000` for the dashboard.

### 5.2 Wrong Python, or a broken venv

Traceback is `ModuleNotFoundError: No module named 'fastapi'`, or the window closes instantly
with *"is not recognized"*.

**Diagnose** (the leading `&` is required — PowerShell treats a bare quoted path as a string,
not a command, and errors with *"Unexpected token '-c'"*):
```powershell
& "d:\Daniyal Files\Traffic_Trace\api\.venv\Scripts\python.exe" -c "import sys, fastapi, psycopg, numpy; print(sys.version)"
```

It must print **3.12.x**. If it prints 3.14, you launched the wrong interpreter — **always**
`.\.venv\Scripts\python.exe`, never a bare `python`. There are no binary wheels for 3.14 and
nothing will import.

**Fix (needs internet — this is a night-before fix, not a demo-morning fix):**
```powershell
cd "d:\Daniyal Files\Traffic_Trace\api"
py -3.12 -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt -r ..\pipeline\requirements.txt
```

### 5.3 Pipeline import failure

Traceback names something inside `pipeline/` — most often `fast_alpr`, `onnxruntime`, `torch`
or `open_clip`.

> **`pipeline/__init__.py` imports `alpr` at module load.** A missing `fast_alpr` breaks the
> **entire** pipeline, not just plate reading. That is the trap.

**Diagnose — this names the exact missing import:**
```powershell
cd "d:\Daniyal Files\Traffic_Trace\api"
.\.venv\Scripts\python.exe -m scripts.preflight
```

Expect a wall of onnxruntime shape warnings while the pipeline imports — **that is normal**,
it is fast_alpr loading its ONNX model. Read the `FAIL` lines, not the warnings. Every FAIL
prints its own fix.

**Fix:** install whatever preflight names, into the venv. **Call Saad** — `pipeline/` is his.
It needs internet, so realistically this is a night-before fix. If it happens on the morning,
the demo runs on the [cold fallback](#option-c--cold-fallback-pipeline-itself-is-down).

### 5.4 Postgres down

Traceback is `connection refused` / `OperationalError` on port 5432, or the API starts but
`/api/health` reports `"db": {"ok": false, ...}`. Go to [§7](#7-postgres-is-not-running).

### The one command that covers all four

```powershell
cd "d:\Daniyal Files\Traffic_Trace\api"; .\.venv\Scripts\python.exe -m scripts.preflight
```

Exit 0 = the machine is ready. Exit 1 = it printed the exact fix for whatever is broken.
**Run it the night before, and again on the morning.**

---

## 6. `pipeline.real == false` — the AI is not running

**Symptom.**
```json
{"pipeline": {"real": false, "status": "stub (pipeline module not present)"}}
```
at `http://127.0.0.1:8000/api/health`. `start_demo.ps1` refuses to say READY and stops here.

### What it means — read this before deciding anything

**The AI is not loaded. Every sighting the system produces is a random number.**

The stub still returns plausible-shaped data: detections appear, sightings are written,
incidents open, candidates get scored, the counters go green. **All of it is invented.** This
is the single worst failure mode in the project precisely because nothing looks broken. It is
why `/api/health` reports this field at all, and why the launcher treats it as fatal.

**Never demo on the stub.** A judge who asks "what did it detect?" gets an answer that is not
true, and you will not know it is not true.

### How to diagnose it (60 seconds)

```powershell
cd "d:\Daniyal Files\Traffic_Trace\api"
.\.venv\Scripts\python.exe -m scripts.preflight
```

Its pipeline section names the missing import. Common causes:

| `status` says | Cause | Fix |
|---|---|---|
| `pipeline module not present` | `pipeline/` folder missing or not beside `api/` | Restore it; the layout must be `Traffic_Trace/{api,pipeline}` |
| an import error naming `fast_alpr` / `onnxruntime` | ALPR deps missing — and that breaks **everything** | `.\.venv\Scripts\pip install fast_alpr onnxruntime` (needs internet) |
| an import error naming `torch` / `open_clip` | pipeline requirements not installed | `.\.venv\Scripts\pip install -r ..\pipeline\requirements.txt` (needs internet) |
| a `FileNotFoundError` on a `.pt` file | model weights missing | Copy `yolov8n.pt` and `helmet_model.pt` from the USB into `pipeline/` |

**Then restart the API.** The import is attempted once at startup, so the health field will
not change until the process restarts: close the `Traffic_Trace API :8000` window and re-run
`start_demo.ps1`.

**If it cannot be fixed before you walk on:** go to
[§14, Option C](#option-c--cold-fallback-pipeline-itself-is-down). Show the exported case-file
PDF and say plainly that the pipeline is not loading on this machine. Honest beats fake.

**Owner: Saad.**

---

## 7. Postgres is not running

**Symptom.** `/api/health` shows `"db": {"ok": false, "error": "connection refused"}`, or
`start_demo.ps1` stops at *"cannot query the database"*.

**Diagnose:**
```powershell
Get-Service postgresql-x64-18
```

**Fix — start it:**
```powershell
Start-Service postgresql-x64-18
```

**If that is refused with an access error,** the shell is not elevated: right-click PowerShell
→ **Run as administrator** → run it again. Or `services.msc` → find **postgresql-x64-18** →
**Start**.

**Verify the database itself answers:**
```powershell
$env:PGPASSWORD='trafficdev'; psql -U postgres -d traffic_trace -c "SELECT count(*) FROM cameras;"
```

`3` is the right answer.

**If the service will not start at all,** the last hundred lines of the Postgres log say why:
`C:\Program Files\PostgreSQL\18\data\log\` — open the newest file. The usual causes are a stale
`postmaster.pid` after a hard power-off (delete it, it is in the `data` folder, then start the
service) or port 5432 taken by something else.

**If the tables are gone** (`relation "cameras" does not exist`):
```powershell
$env:PGPASSWORD='trafficdev'
psql -U postgres -d traffic_trace -f "d:\Daniyal Files\Traffic_Trace\contracts\schema.sql"
psql -U postgres -d traffic_trace -f "d:\Daniyal Files\Traffic_Trace\contracts\migrations\001_fix_empty_embedding_check.sql"
cd "d:\Daniyal Files\Traffic_Trace\api"; .\.venv\Scripts\python.exe -m scripts.seed_cameras
```

**⚠️ Re-seeding creates NEW tokens.** Every phone must be re-claimed with the new secrets,
which `seed_cameras.py` prints. Budget three minutes and do it before stage, never during.

> **There is no Docker fallback on this laptop and there never will be.** Do not spend demo
> minutes trying. See PROGRESS.md §4.2.

---

## 8. Database has junk from testing

**Symptom.** The incident feed is full of rehearsal violations, the map is covered in old
markers, or the journey picker lists incidents from yesterday.

### The reset button (10 seconds)

Dashboard sidebar → enter the officer PIN **4321** → **Unlock** → **Reset demo** → confirm.
The page reloads into a clean state.

### The API call behind it

```
POST /api/admin/reset
Header: X-Officer-Pin: 4321
```

From PowerShell, if the browser is being awkward:

```powershell
curl.exe -s -X POST http://127.0.0.1:8000/api/admin/reset -H "X-Officer-Pin: 4321"
```

Returns `{"sightings_deleted": N, "crops_deleted": M}`.

**What it does:** one `DELETE FROM sightings` — incidents, matches and journeys all cascade
from it — plus every `.jpg` in `evidence/`.

**What it deliberately does NOT delete: the three cameras and their tokens.** Their secrets
are already typed into three phones, and re-registering mid-demo costs minutes you do not
have. That is what makes reset safe to press at any time, including thirty seconds before you
walk on.

**Confirm it worked:**
```powershell
$env:PGPASSWORD='trafficdev'; psql -U postgres -d traffic_trace -c "SELECT (SELECT count(*) FROM sightings) AS sightings, (SELECT count(*) FROM incidents) AS incidents, (SELECT count(*) FROM cameras) AS cameras;"
```

Expect `0 | 0 | 3`.

**If the PIN is rejected:** it is read from `OFFICER_PIN` in `api/.env`. Check it with
`findstr OFFICER_PIN "d:\Daniyal Files\Traffic_Trace\api\.env"`. If the sidebar shows no PIN
box at all, reload the page — the PIN lives in `sessionStorage` and a closed window re-locks
it.

---

## 9. No candidates for an incident

**Symptom.** An incident opens, the review screen loads, the candidate list is empty or has
one useless entry. The API window logs the incident line but no
`incident <id>: N candidates, best …` line, or `N` is 0.

**Check these in order. Each takes seconds.**

### 9.1 Are there any other sightings at all?

```powershell
$env:PGPASSWORD='trafficdev'; psql -U postgres -d traffic_trace -c "SELECT c.name, count(*), min(s.ts), max(s.ts) FROM sightings s JOIN cameras c ON c.id=s.camera_id GROUP BY c.name;"
```

If only one camera has rows, the other two phones are not sending — go to
[§1](#1-phone-dies-or-will-not-stream) / [§3](#3-phone-cannot-reach-the-laptop).
**Matching compares a violation against sightings from OTHER cameras. With one camera
streaming there is nothing to match against.** This is the most common cause by a wide margin.

### 9.2 The 30-minute window

The space-time gate only looks **±30 minutes** around the violation
(`MATCH_WINDOW_SECONDS = 30 * 60` in `api/app/core/constants.py`). Sightings from a rehearsal
an hour ago are invisible to it, on purpose — beyond that a "match" stops being evidence of a
journey and starts being a coincidence.

**What this means for the demo:** the reappearance pass must happen **within 30 minutes** of
the violation. In a 7-minute demo that is never the live problem — but it is exactly why a
violation left over from rehearsal never gets candidates from the live run. **Reset before you
start** ([§8](#8-database-has-junk-from-testing)).

### 9.3 Cameras too far apart

The gate enforces **60 km/h maximum, 30 s grace**. Two cameras 4 km apart need at least ~210 s
between sightings before a match is even physically possible. Ride past both in 30 seconds and
the gate correctly rejects it: no vehicle could have done that.

**Check the real distances:**
```powershell
cd "d:\Daniyal Files\Traffic_Trace\api"; .\.venv\Scripts\python.exe -m scripts.seed_cameras
```

It is idempotent and prints the pairwise distances plus the minimum travel time each pair
enforces. **Target 1–2 km spacing** — that gives 52–96 s minimum gaps, which a rider beats
comfortably inside a demo.

**With the currently seeded (placeholder) positions:**

| Pair | Distance | Minimum gap the gate enforces |
|---|---|---|
| Camera 1 → Camera 2 | 1.37 km | 52 s |
| Camera 1 → Camera 3 | 1.62 km | 67 s |
| Camera 2 → Camera 3 | 2.10 km | 96 s |

**`docs/PITCH.md` slide 4 and `docs/DEMO_SCRIPT.md` segment 6 both quote the Camera 1 →
Camera 3 pair (1.6 km / 67 s) out loud.** If the camera locations change, re-run the command
above and update both scripts — the pins are on the projected map and a judge can see when
the number does not match the picture.

**The classic version of this failure:** a bad GPS fix put one camera kilometres from where it
actually is, so nothing is reachable from anything. Open `/map` — if a pin is in the wrong
place, fix it on that phone's locate step ([§4](#4-camera-or-gps-permission-denied)).

### 9.4 The candidates are all the same vehicle

Not a gate failure. **`dedupe` is still a placeholder on Saad's side** (his Phase 14). Without
it, ten consecutive frames of one motorcycle become ten near-identical candidates and crowd
out genuinely different sightings. A top score sitting at exactly `1.0000` is this: the same
vehicle from a second frame of the same pass, so the embeddings are literally identical.

**Nothing to fix on stage.** If a judge notices, the honest answer is the good one: *"Burst
de-duplication is next on the pipeline list — right now consecutive frames of one vehicle each
count as a candidate. It doesn't change which vehicle wins, it just makes the list longer than
it should be."*

### 9.5 The reappearance never alerted — because the incident was already confirmed

**This is the one that will bite you, and it produces no error of any kind.**

Two separate things put candidates on an incident:

| | When it runs | What it needs |
|---|---|---|
| **Match engine** | once, the instant the incident opens | sightings that already exist |
| **Watchlist** | on every new sighting afterwards | the incident status to still be **`open`** |

`get_open_for_watchlist` filters on `WHERE i.status = 'open'`, and the **first Confirm on an
incident sets its status to `confirmed`.** From that click on, no later sighting will ever be
attached to that incident and no reappearance toast will ever fire for it.

**So the order is: ride the reappearance first, confirm second.** `docs/DEMO_SCRIPT.md` Part
2 is sequenced that way on purpose — segment 7 is the ride, segment 8 is the confirm.

**Also worth knowing:** a watchlist hit is only saved when it scores **≥ 0.6**
(`WATCHLIST_ALERT_THRESHOLD` in `pipeline/matcher.py`). Below that, nothing is written and
nothing is shown. There is no "it was recorded but not alerted" state to fall back on — do
not claim there is.

**If you already confirmed and need the alert back**, reopen the incident:

```powershell
$env:PGPASSWORD='trafficdev'; psql -U postgres -d traffic_trace -c "UPDATE incidents SET status='open' WHERE status='confirmed';"
```

Confirmed matches survive that, so the journey stays intact. Never run it mid-segment; it is
a between-runs fix.

### 9.6 It fell back to visual ranking

Log line: `score_candidates returned nothing; falling back to visual ranking`.

Saad's scorer raised or returned empty, and the API is showing its own CLIP-cosine ranking
instead. **This is a designed fallback — a degraded review screen beats a blank one.** The list
will be noisier than usual because CLIP alone cannot tell two motorcycles apart (a
different-vehicle pair once scored 0.9179 against a same-vehicle pair at 0.8703). Carry on and
tell Saad afterwards.

---

## 10. Matching or ingest is slow

**Symptom.** `Server queue` climbing on the phone, `dropped` non-zero at
`http://127.0.0.1:8000/api/frames/stats`, incidents appearing many seconds after the pass.

**Check:**
```powershell
curl.exe -s http://127.0.0.1:8000/api/frames/stats
```

`processed` / `dropped` / `failed`. A non-zero `dropped` means inference is behind and the
bounded queue (**8 frames**) is shedding load — **by design**: under overload it drops frames
rather than memory, so it degrades instead of dying.

The queue is deliberately shallow, because its depth *is* the delay before a frame is
looked at. At the measured ~1.2 frames/s, 8 frames is a ~7-second wait; the old 64 was a
**54-second** one, and a violation frame posted into a busy queue was evicted by newer
arrivals before it was ever processed — the incident simply never appeared. Measured with
two cameras streaming a busy street: **19.3 s to the incident at 64, 5.1 s at 8.**
**A high `dropped` with a low latency is the system working correctly.**

### What to do, in order (all under 10 seconds)

1. **Stop moving.** Extra passes make it worse. One vehicle, one pass.
2. **Stop streaming on the cameras you are not using at that instant.** Three phones into a
   CPU pipeline is three times the work. Tap **Stop** on two phones.
3. **Wait.** The queue drains. It is 8 frames — about seven seconds, not minutes.

### What NOT to do

- **Do not kill and restart the API to "clear it".** You lose the queue, every WebSocket
  connection, and the model reload: **measured 10.3–16.0 s** before `/api/health` answers
  (cold 16.0 s, warm ~10.5 s — `docs/STATS.md` §6). Both models load at import, so uvicorn
  is not "up" until YOLOv8n, the helmet model and CLIP are all in memory.
- **Do not change the capture interval or the queue size** mid-demo.

### This laptop is genuinely slower than three phones at full rate

Measured (`docs/STATS.md` §2): **1.56 s median for one frame** through the whole worker job,
**0.72 fps sustained**. Three phones at one frame every two seconds ask for **1.5 fps** —
roughly **2.1× more than this machine can process**. At that rate the 8-frame queue fills in
about **10 seconds** and eviction starts — which is intended: it is what keeps the frames
that *do* get processed recent.

So a climbing `dropped` under three-phone load is **expected behaviour, not a fault.** Reduce
the load (below) rather than hunting for a bug. The camera page only streams at full rate when
it sees motion, which is why this does not bite on a quiet street.

### If you suspect the matching rather than the inference

Matching is not the slow part — **≈40 ms end to end** against 5,000 sightings (SQL gate
~36.5 ms, numpy cosine ~1 ms; `docs/STATS.md` §1 measured 37.8 ms, the Phase 3 log 37.2 ms and
the post-audit log 43.4 ms, all on a machine also running Postgres — quote "about 40
milliseconds", not a decimal). If you genuinely need to prove it, the acceptance test is:

```powershell
cd "d:\Daniyal Files\Traffic_Trace\api"; .\.venv\Scripts\python.exe -m scripts.bench_matching
```

It cleans up after itself. **Do not run it while the demo is live** — it inserts thousands of
rows. Night-before only.

**Say while it drains:** *"That queue number is the system protecting itself — under load it
drops frames rather than memory, so it degrades instead of dying. In a real deployment this is
a GPU box, not a laptop running three models on a CPU."*

---

## 11. Map is blank

**Symptom.** `/map` or `/journeys` shows grey squares where the map should be. Markers and the
route may still draw correctly on top of the grey — that is the giveaway that it is a tile
problem, not a code problem.

**Cause: the offline tile cache is missing or incomplete.** The venue has no internet, so
Leaflet cannot fetch tiles and renders empty grey.

**Diagnose:**
```powershell
(Get-ChildItem "d:\Daniyal Files\Traffic_Trace\dashboard\public\tiles" -Recurse -File -Filter *.png).Count
```

**528** is the expected number. `0` means the cache is gone.

**The fix — read the warning before trying it:**
```powershell
cd "d:\Daniyal Files\Traffic_Trace\api"; .\.venv\Scripts\python.exe -m scripts.download_tiles
```

> ### ⚠️ `download_tiles.py` NEEDS INTERNET. It cannot be run at the venue.
> This is not fixable on stage. If the tiles are gone and there is no internet, the map pages
> are lost for this run — **skip them and keep going.** The incident feed, the review screen,
> the case file and the confirm flow all work without a single tile.

**Restore from USB instead.** The tile cache is gitignored in **both** repos, so a fresh clone
has no tiles at all:

```powershell
robocopy "E:\TrafficTrace_Backup\Traffic_Trace\dashboard\public\tiles" "d:\Daniyal Files\Traffic_Trace\dashboard\public\tiles" /E
```

> That is where [§F2](#f2--the-usb-stick)'s whole-folder `robocopy` puts them. Check the path
> on the stick before trusting it — `robocopy` reports **exit 1 on success** (it means "files
> were copied"), so a non-zero exit code here is not a failure. Exit 0 means nothing needed
> copying, and anything ≥ 8 is a real error.

No rebuild is needed — `public/` is served as static files, not compiled into the bundle.

**If the tile count is right but the map is still grey:** the cameras were moved to new
coordinates and the cache covers the old area. Same fix, same internet requirement. **This is
why the camera locations must be frozen before the last tile download.**

---

## 12. Journey does not appear

**Symptom.** `/journeys` has nothing to select, or an incident's journey returns `404`.

**This is correct behaviour, not a bug.** `GET /api/journeys/{incident_id}` returns 404 until
**at least one candidate has been CONFIRMED** on that incident. A journey is built from
confirmed matches only — the officer's decision is what creates it, which is the whole point of
the product.

### The 20-second fix

1. Go to `/incidents` → open the incident.
2. If the Confirm button does nothing, sidebar → PIN **4321** → **Unlock**.
3. Pick the right candidate → **Confirm** (or press `c`).
4. Go back to `/journeys`. The incident is now in the picker.

**The Confirm button silently doing nothing = the PIN is not unlocked in this browser
window.** The PIN lives in `sessionStorage`, so a closed window or a new tab re-locks it.

**Cover it as a feature, because it is one:** *"Confirming is PIN-gated. The read-only screens
stay open so they can be projected, but anything that changes a case needs an officer to
authorise it."*

**Verify from the database if you need certainty:**
```powershell
$env:PGPASSWORD='trafficdev'; psql -U postgres -d traffic_trace -c "SELECT incident_id, count(*) FILTER (WHERE decision='confirm') AS confirmed FROM matches GROUP BY incident_id;"
```

**A journey never has fewer than two stops.** `rebuild_journey` returns nothing until the
violation *plus at least one confirmed match* exist, and `GET /api/journeys/{id}` 404s until
then — so "one stop" is not a state you can reach. If you want a third stop, confirm a third
candidate.

**Stops are ordered by capture time, not by role.** `build_journey` sorts on `ts`, so if a
confirmed sighting was captured *before* the violation — the warm-up pass, typically — it is
drawn as stop 1 and the violation is stop 2. That is correct: the route is the vehicle's
timeline, not our discovery order. Say so if a judge asks; do not claim the violation is
always first.

---

## 13. Laptop dies

**The demo laptop is a single point of failure and nothing in this document changes that.**
What follows only works if the backup was prepared while there was internet.

### What must already be on the backup laptop (prepared the night before, WITH internet)

| Must be installed | Why it cannot be done at the venue |
|---|---|
| **PostgreSQL 18** (native service `postgresql-x64-18`), password `trafficdev`, database `traffic_trace` created | The installer needs downloading, and no Docker fallback exists |
| **Python 3.12** reachable as `py -3.12` | 3.14 has no binary wheels; installing 3.12 needs internet |
| **Node 22** | `npm install` needs the registry |
| **The full project folder including `api\.venv`, `dashboard\node_modules` and `dashboard\.next`** | `pip install` and `npm install` both need internet — a git clone alone will not run |
| **Schema applied and 3 cameras seeded** | The tokens must match what is already typed into the phones |
| Chrome | — |

### What must be on the USB

See [freeze checklist §F2](#f2--the-usb-stick). The three items that are **not in either git
repo** and will silently be missing from a fresh clone:

1. **`api/.env`** — gitignored. Without it the API has no `DATABASE_URL` and no `OFFICER_PIN`,
   and will not start.
2. **`dashboard/public/tiles/`** — gitignored in both repos. Without it every map is grey.
3. **`api/.venv/`, `dashboard/node_modules/`, `dashboard/.next/`** — gitignored, and
   unrecoverable without internet.

### The switch (target: 4 minutes)

1. Plug the USB into the backup laptop. Copy the folder to `d:\Daniyal Files\Traffic_Trace`.
   The drive letter does not matter, but the `api/` ↔ `pipeline/` ↔ `dashboard/` sibling layout
   does — `api/` imports `pipeline/` as a sibling.
2. Confirm `api\.env` exists and `DATABASE_URL` points at `127.0.0.1:5432/traffic_trace`.
3. `cd "d:\Daniyal Files\Traffic_Trace"; .\start_demo.ps1`
4. It prints a **new LAPTOP IP**. Every phone's Chrome flag must contain it — which is why the
   flag should already list every plausible hotspot address
   ([§3](#step-2--fix-the-chrome-flag-on-each-phone-30-seconds-per-phone)).
5. If the backup laptop's database was seeded separately, **its tokens are different.** Re-claim
   each phone with the tokens `start_demo.ps1` prints.

**Say while doing it:** *"We're moving to the backup machine. The whole system is one folder
and a Postgres database — which is part of the point: this deploys to a laptop in a police
station, not a data centre."*

**If there is no backup laptop and no time:** go straight to
[§14, Option C](#option-c--cold-fallback-pipeline-itself-is-down) — the exported PDF case file
and the journey screenshot, shown from a phone if necessary.

---

## 14. Live demo is going badly — switch to replay

### Decide by 30 seconds. Do not attempt a third pass.

If the incident has not appeared 30 seconds after the violation pass, **switch**. A third
attempt burns two minutes and the audience watches you lose.

### Say this, once, without apologising

> **"We're going to run this on recorded footage instead — this is the same pipeline running on
> this morning's recording, frame for frame. Nothing behind it changes."**

**That statement is literally true.** `POST /api/frames` cannot tell a phone from a replay: the
camera is identified by the `X-Camera-Token` header and nothing else. Same endpoint, same
queue, same worker, same models, same database. Say it with a straight back — judges respect a
prepared fallback far more than a phone that happens to work.

### Option A — `tools/replay.py`

> ✅ **Delivered and verified end to end on 29 Aug** — 3 frames sent, 3 accepted,
> 11 sightings and 4 incidents produced. Still rehearse it once in Phase 19 against
> your own recording.

```powershell
cd "d:\Daniyal Files\Traffic_Trace"
.\api\.venv\Scripts\python.exe tools\replay.py --folder tools\recordings --cameras cam-A,cam-B,cam-C --api-url http://127.0.0.1:8000/api/frames
```

Tokens come from `tools\tokens.json`, written by `scripts\seed_cameras.py` with the
keys `cam-A`/`cam-B`/`cam-C`. It needs one folder per camera, each holding the frames
plus a `manifest.json`:

```json
[
    {"file": "frame_001.jpg", "ts": "2026-08-22T14:00:00Z"},
    {"file": "frame_002.jpg", "ts": "2026-08-22T14:00:02Z"}
]
```

The original inter-frame timing is preserved. `--speed 5` plays it five times faster,
`--dry-run` prints what it would send without posting anything. One thread per camera,
so three cameras replay concurrently exactly as three phones would.

`tools\test_recordings\cam-A` holds 3 sample frames — use them to prove the command
works before you need it:

```powershell
.\api\.venv\Scripts\python.exe tools\replay.py --folder tools\test_recordings --cameras cam-A --api-url http://127.0.0.1:8000/api/frames
```

### Option B — saved frames over curl (works today, exactly as the endpoint is built)

**Have this pre-typed in a third PowerShell window before you walk on.** One Enter and it runs.

```powershell
function Send-Replay {
  param([string]$Token, [string]$Dir, [int]$MinutesAgo)
  $t = (Get-Date).ToUniversalTime().AddMinutes($MinutesAgo)
  Get-ChildItem "$Dir\*.jpg" | ForEach-Object {
    $stamp = $t.ToString("yyyy-MM-ddTHH:mm:ssZ")
    curl.exe -s -X POST http://127.0.0.1:8000/api/frames -H "X-Camera-Token: $Token" -F "frame=@$($_.FullName)" -F "ts=$stamp" | Out-Null
    $t = $t.AddSeconds(2)
    Start-Sleep -Milliseconds 400
  }
}

$root = "d:\Daniyal Files\Traffic_Trace\demo_frames"
Send-Replay -Token "<CAM2_TOKEN>" -Dir "$root\cam2" -MinutesAgo -4   # background traffic
Send-Replay -Token "<CAM1_TOKEN>" -Dir "$root\cam1" -MinutesAgo -2   # the violation
Send-Replay -Token "<CAM3_TOKEN>" -Dir "$root\cam3" -MinutesAgo  0   # the reappearance
```

**Three things make this the strongest fallback in the document — and one of them is a trap:**

- It posts to `127.0.0.1`, so **it does not touch the network at all.** It survives the hotspot
  dying completely.
- **`-F "ts=..."` is not optional.** `ts` is the *capture* time and it is what the space-time
  gate reasons about. Leave it out and the endpoint stamps every frame with its arrival time,
  so all three cameras land within seconds of each other, the gate correctly rules that no
  vehicle covered 1.4 km in four seconds, and you get an incident with **zero candidates and
  no journey** — a fallback that appears to run perfectly and produces nothing. The −4 / −2 / 0
  offsets leave ~120 s between cameras, comfortably over the 52–96 s the gate demands at the
  seeded spacing.
- The 400 ms sleep is not decoration either. Fire every frame at once and the 8-frame queue
  starts **evicting the oldest queued frame** to make room (that is the documented, deliberate
  direction — see `app/workers/frame_worker.py`), which during a replay means the beginning of
  the ride, where the violation pass usually is.

**Run all three blocks before confirming anything** — the first confirm closes the incident to
the watchlist ([§9.5](#95-the-reappearance-never-alerted--because-the-incident-was-already-confirmed)).

### Option C — cold fallback (pipeline itself is down)

If `/api/health` says `pipeline.real: false` and it cannot be fixed: **do not run the stub in
front of judges.** Open the case-file PDF you exported the night before and walk through it:

> *"Our AI process isn't loading on this machine right now, so rather than show you something
> fake, here's a case this system produced this morning — same screens, same evidence, same
> hashes."*

**Prepare this the night before: one exported case-file PDF on the desktop, one screenshot of a
completed journey map.** Two files. If you never need them, you lost five minutes.

### If you are simply running out of time

Cut in this order:
1. Segment 3 (registering a camera) — show the map instead.
2. Segment 10 (case file) — mention SHA-256 in one line during segment 9.
3. Segment 8's reject-then-confirm — just confirm.

**Never cut segment 7 (the reappearance) or segment 9 (the journey).** Those two are why the
project exists — and never reorder them so a confirm lands before the reappearance ride
([§9.5](#95-the-reappearance-never-alerted--because-the-incident-was-already-confirmed)).

---
---

# FREEZE CHECKLIST

> **Freeze means: no more code changes.** From the moment you tag, the only edits allowed are
> ones that fix a failure found at rehearsal — and every one of them gets re-tagged and
> re-copied to the USB. A last-minute "small improvement" is how demos die.
>
> Do all of §F1–§F5 **the night before, while there is still internet.** None of it can be done
> at the venue.

---

## F1 — Tag and push both repos

**Daniyal runs every git command himself.** These are the commands to paste:

```powershell
# Backend
cd "d:\Daniyal Files\Traffic_Trace"
git add -A
git commit -m "Phase 20: freeze for regional round"
git tag -a demo-freeze -m "Regional round demo build, 28 Aug 2026"
git push origin main
git push origin demo-freeze

# Frontend
cd "d:\Daniyal Files\Traffic_Trace\dashboard"
git add -A
git commit -m "Phase 20: freeze for regional round"
git tag -a demo-freeze -m "Regional round demo build, 28 Aug 2026"
git push origin main
git push origin demo-freeze
```

- [ ] Backend pushed and tagged — `https://github.com/UniDev143/Traffic-Trace-Backend.git`
- [ ] Frontend pushed and tagged — `https://github.com/UniDev143/Traffic-Trace-Frontend.git`
- [ ] **Both repos still PRIVATE.** `PROGRESS.md` contains the local DB password and the
      officer PIN.
- [ ] `pipeline/yolov8n.pt` and `pipeline/helmet_model.pt` are **in** the backend repo. `*.pt`
      is ignored but these two are explicitly un-ignored — verify with
      `git ls-files pipeline/*.pt`. A backup of something that does not run is not a backup.
- [ ] Prove the tag restores: clone both repos into a scratch folder and confirm the layout is
      `Traffic_Trace/{api,pipeline,contracts,tools}` with `dashboard/` inside it.

---

## F2 — The USB stick

### ⚠️ The trap: what git does NOT have

A fresh clone of both repos **will not run.** These are gitignored and exist only on this
laptop:

| Missing from git | What breaks without it | Where it lives |
|---|---|---|
| **`api/.env`** | The API cannot find the database or the officer PIN. It will not start. | `api\.env` |
| **`dashboard/public/tiles/`** (528 png, 3.5 MB) | Every map page is grey squares, and re-downloading **needs internet** | `dashboard\public\tiles\` |
| **`api/.venv/`** | `pip install` needs internet | `api\.venv\` |
| **`dashboard/node_modules/`** | `npm install` needs internet | `dashboard\node_modules\` |
| **`dashboard/.next/`** | The build works offline, but costs 40 s you may not have | `dashboard\.next\` |
| **`demo_frames/`** (the golden recording) | The Option B fallback has nothing to replay | `demo_frames\cam1..3\` |

`api/.env.example` **is** committed, so the shape of the file is recoverable — but the password
and the PIN are not. Copy the real `.env`.

### Copy the whole folder. Do not be clever about it.

```powershell
robocopy "d:\Daniyal Files\Traffic_Trace" "E:\TrafficTrace_Backup\Traffic_Trace" /E /R:1 /W:1 /XD .git __pycache__
```

Keeping `.venv`, `node_modules`, `.next` and `public\tiles` is the entire point — excluding
them is exactly what makes an offline restore impossible. Excluding `.git` keeps it small: the
repos are the version-history backup, the USB is the *runs-without-internet* backup.

### Then add, in a folder next to it

- [ ] `api\.env` copied out separately as well, so it is obvious and findable in a panic
- [ ] `demo_frames\cam1\`, `cam2\`, `cam3\` — the golden recording. **Captured at the dress
      rehearsal. You cannot make these on stage.**
- [ ] `tools\recordings\cam-A|cam-B|cam-C\` — frames + `manifest.json` per camera, for `replay.py`
- [ ] `scripts\smoke_demo.py` run and green (52 checks, end to end through the real API).
      Destructive — run it **before** the phones are set up, never during.
- [ ] **One exported case-file PDF** (open an incident → **Case file** → print to PDF)
- [ ] **One screenshot of a completed journey map** showing a 3-stop route
- [ ] `docs\RUNBOOK.md` (this file), `docs\DEMO_SCRIPT.md`, `docs\PITCH.md` as PDFs
- [ ] The pitch deck
- [ ] Note: `contracts\schema.sql` and `contracts\migrations\` are already inside the folder
      copy — listed here so you know where they are if you ever rebuild a database by hand

### Two sticks, two people

- [ ] Stick 1 with Daniyal
- [ ] Stick 2 with Saad
- [ ] **Verify the copy on a different machine.** Plug it in, open `api\.env`, count the tiles.
      An unverified backup is a rumour.

---

## F3 — Paper

Screens fail. Paper does not.

- [ ] **The token card**, printed, one per person: each camera's **name**, **token** and
      **surveyed lat/lng** (needed when GPS fails), the **officer PIN 4321**, and the **laptop
      IP plus the exact Chrome flag string**.
- [ ] This runbook, printed.
- [ ] `docs/DEMO_SCRIPT.md` Part 2 (the segment timings), printed.

Regenerate the token card if the cameras are ever re-seeded:
```powershell
$env:PGPASSWORD='trafficdev'; psql -U postgres -d traffic_trace -c "SELECT name, token, lat, lng FROM cameras ORDER BY name;"
```

---

## F4 — Phones: what to charge, what to disable

### Hardware

- [ ] 3 camera phones **at 100%**
- [ ] 1 spare phone **at 100%**, already claimed to a camera and left on the streaming screen
- [ ] 1 hotspot phone **at 100%** — this one drains fastest, it is doing the WiFi
- [ ] Laptop at 100% **and plugged in**, with its charger and an extension lead
- [ ] 2 power banks charged, plus a cable per phone
- [ ] Tripods / mounts, and something to weigh them down outdoors

### Settings to change on every phone — each of these has killed a capture loop

- [ ] **Battery saver / power saving: OFF.** It throttles JavaScript timers and revokes the
      wake lock. This is the number-one silent capture killer.
- [ ] **Adaptive / Auto battery: OFF** for Chrome specifically.
- [ ] **Screen timeout: maximum** (30 min or Never). The page holds a wake lock, but Android
      drops it when the tab is backgrounded and never restores it on its own.
- [ ] **Do Not Disturb: ON.** An incoming call backgrounds Chrome and stops the stream.
- [ ] **Auto-rotate: OFF**, locked in the orientation you rehearsed in.
- [ ] **Auto-brightness: OFF**, brightness high — you must be able to read the counters
      outdoors.
- [ ] **Chrome Lite mode / Data Saver: OFF.** It rewrites requests.
- [ ] **System and app auto-updates: OFF.** A Chrome update overnight can reset flags.
- [ ] **Chrome flag `unsafely-treat-insecure-origin-as-secure`** set to a **comma-separated
      list of every IP the hotspot has ever handed out**, each with `:3000`. Relaunch Chrome
      afterwards.
- [ ] **Close every other Chrome tab.** Background tabs compete for memory and the camera.
- [ ] **Close every other camera app.** Android hands the camera to one app at a time.
- [ ] Camera lens **wiped clean**. Genuinely: a smeared lens degrades detection.
- [ ] Token pasted and claimed, GPS saved, **● JS ready** green, one test frame sent.

### The hotspot phone

- [ ] Hotspot name and password written on the token card
- [ ] **"Turn off hotspot automatically when no devices are connected": OFF.** It will switch
      itself off between setup and demo otherwise.
- [ ] Laptop connected to it, confirmed with `ipconfig`
- [ ] Mobile data can be off — nothing needs the internet. The hotspot is a LAN, not a link to
      anywhere.

---

## F5 — The night before, on the laptop

- [ ] `cd "d:\Daniyal Files\Traffic_Trace\api"; .\.venv\Scripts\python.exe -m scripts.preflight`
      → **exit 0, zero FAILs**
- [ ] `.\start_demo.ps1` runs clean start to finish and prints **READY**
- [ ] `/api/health` shows `"pipeline": {"real": true, ...}` and `"db": {"ok": true, ...}`
- [ ] `dashboard\.next\BUILD_ID` exists — the production build is already built, so demo
      morning does not spend 40 s on `npm run build`
- [ ] Tile count is **528**
- [ ] Camera coordinates are the **final** ones, and the tiles were downloaded **after** they
      were set
- [ ] Full walk-through: phone → violation → incident → review → confirm → journey →
      reappearance. **All of it, with your own eyes, in one run.**
- [ ] Case-file PDF exported to the desktop; journey screenshot saved
- [ ] USB copies made and verified on a second machine
- [ ] Laptop: Windows Update paused, notifications off, sleep/hibernate disabled, screen timeout
      Never, browser zoom set for the projector, bookmarks bar hidden
- [ ] Everything charging overnight

---

## F6 — Morning of: go / no-go

**Run in this order. Any NO-GO gets fixed before you walk on, or you plan for the fallback.**

| # | Check | GO looks like | NO-GO → |
|---|---|---|---|
| 1 | `Get-Service postgresql-x64-18` | `Running` | [§7](#7-postgres-is-not-running) |
| 2 | `.\.venv\Scripts\python.exe -m scripts.preflight` | exit 0, no FAIL | [§5](#5-api-will-not-start) |
| 3 | `.\start_demo.ps1` | prints **READY** and a LAPTOP IP | read its FIX line |
| 4 | `curl.exe -s http://127.0.0.1:8000/api/health` | `db.ok: true` **and** `pipeline.real: true` | [§6](#6-pipelinereal--false--the-ai-is-not-running) |
| 5 | Tile count | 528 | [§11](#11-map-is-blank) |
| 6 | Laptop IP matches the Chrome flag on **all** phones | exact string match, incl. `:3000` | [§3](#3-phone-cannot-reach-the-laptop) |
| 7 | All 3 phones claimed, streaming, **● JS ready** green | green on all three | [§2](#2-red-js-not-running-banner) |
| 8 | Each phone's own counters: `Frames sent` climbing, `Last ack` < ~2 s | climbing on all three | [§1](#1-phone-dies-or-will-not-stream) / [§3](#3-phone-cannot-reach-the-laptop) |
| 9 | **Reset demo** (PIN 4321) — this comes **before** the warm-up | feed empty, 3 cameras kept | [§8](#8-database-has-junk-from-testing) |
| 10 | Warm-up pass past all 3 cameras, **wearing a helmet** | sightings appear, each `/map` pin greens as he passes, **no** incident | an incident means helmet detection missed — tell Saad, then reset again |
| 11 | `curl.exe -s http://127.0.0.1:8000/api/frames/stats` | `dropped: 0`, `failed: 0` | [§10](#10-matching-or-ingest-is-slow) |
| 12 | Fallback window open, curl block pre-typed | one Enter away | [§14](#option-b--saved-frames-over-curl-works-today-exactly-as-the-endpoint-is-built) |
| 13 | Case-file PDF + journey screenshot on the desktop | both open | export them now |
| 14 | Printed token card in hand | in hand | print it |
| 15 | Spare phone claimed, charged, in Saad's pocket | on the streaming screen | [§1](#1-phone-dies-or-will-not-stream) |

**The two that are absolutely non-negotiable: #4 (`pipeline.real: true`) and #9 (reset).**
A stub pipeline means everything you show is invented. Skipping the reset means judges watch
you scroll past yesterday's rehearsal to find today's incident.

> ⚠️ **Reset BEFORE the warm-up, never after** — that is why #9 comes before #10. The warm-up
> sightings are the candidate pool the violation gets matched against; reset after them and
> segment 6's review screen has an empty candidate list. An empty *incident feed* is the right
> starting state, an empty *sightings table* is not. Only reset a second time if the warm-up
> accidentally opened an incident.

---

## The three sentences to have ready

Whatever breaks, one of these covers it. Say it calmly and keep moving.

1. *"That's the connection indicator, not the system — the cameras keep capturing and retrying,
   and it recovers on its own."*
2. *"We're going to run this on recorded footage instead — same pipeline, frame for frame.
   Nothing behind it changes."*
3. *"Rather than show you something fake, here's a case this system produced this morning —
   same screens, same evidence, same hashes."*
