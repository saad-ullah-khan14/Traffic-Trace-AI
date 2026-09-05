# Traffic_Trace — 7-Minute Demo Script

> **Who this is for.** Daniyal and Saad, standing in front of judges, with three phones, a
> laptop, and no internet. Read it once the day before, once on the morning, and keep it
> open on a phone during setup.
>
> **Roles, fixed. Do not swap on the day.**
>
> | | |
> |---|---|
> | **Daniyal** | Drives the laptop. Owns the dashboard, the clicks, the story, and the recovery. Never leaves the laptop. |
> | **Saad** | Owns the phones and the bike. Rides the passes. Speaks for the AI. Carries the spare phone in his pocket. |
>
> **The single most important rule:** if something breaks, **Daniyal keeps talking** while
> Saad fixes it. Silence is what judges remember. Every segment below has a line to say
> while something is loading, because dead air is the only failure that is guaranteed to
> hurt you.

---

## Part 1 — The five minutes before you walk on

Do these **in this order**. The order matters: the reset wipes the warm-up, so reset first.

### Power and hardware

- [ ] Laptop on mains. Not battery. Windows power plan on **High performance** — the AI is
      CPU-only and a throttled laptop is a slow demo.
- [ ] Three phones above **80%**. Power bank in Saad's bag.
- [ ] Phone screens set to **never sleep** (the page holds a wake lock, but belt and braces).
- [ ] **Do Not Disturb on all three phones and on the laptop.** A WhatsApp banner over the
      projected screen is a bad memory.
- [ ] Tripods / clamps placed, angles checked, phones landscape and steady.

### The network

- [ ] Hotspot up. Note the laptop's address on it:
      ```powershell
      ipconfig
      ```
      Write it on your hand. Everything below uses it as `<IP>`.
- [ ] Each phone's Chrome must have the flag
      `unsafely-treat-insecure-origin-as-secure` containing the **exact** origin including
      the port — `http://<IP>:3000`. It gates **both** the camera and the GPS. If the IP
      changed since the last time, the flag is now wrong and both will silently fail.

### The stack

- [ ] Postgres is a Windows service and autostarts. Verify by starting the API rather than
      by checking the service.
- [ ] **Terminal 1 — API:**
      ```powershell
      cd "d:\Daniyal Files\Traffic_Trace\api"
      .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
      ```
- [ ] **Terminal 2 — dashboard. Production build. Never `npm run dev`:**
      ```powershell
      cd "d:\Daniyal Files\Traffic_Trace\dashboard"
      npm run build
      npm run start -- -H 0.0.0.0 -p 3000
      ```
      `npm run dev` ships ~4 MB of JavaScript and never finishes hydrating over a hotspot.
      The page renders and every button silently does nothing. This has already cost us a
      day once.
- [ ] **Open `http://<IP>:8000/api/health` and read it.** Two things must be true:
      - `db.ok` is `true`
      - `pipeline.real` is **`true`**

      > ⚠️ If `pipeline.real` is `false`, the AI did not load and the system is running on
      > the **stub** — it will produce plausible-looking incidents built from random
      > numbers. **Do not demo in that state.** Fix the import or go straight to the
      > fallback in Part 4.

### Tokens and the officer PIN

- [ ] Get the current camera tokens (they change if the cameras were re-seeded):
      ```powershell
      $env:PGPASSWORD='trafficdev'; psql -U postgres -h 127.0.0.1 -d traffic_trace -c "SELECT name, token FROM cameras;"
      ```

      > Without the `PGPASSWORD` prefix `psql` stops on an interactive password prompt.
      > Not what you want with judges in the room.
      Copy the three tokens into a note on each phone, or use a QR — do not retype 32
      characters on stage.
- [ ] On the laptop browser, in **the exact window you will project**, open
      `http://localhost:3000`, enter officer PIN **4321** in the sidebar, click **Unlock**.
      The sidebar must show **● officer unlocked**.

      > The PIN lives in `sessionStorage`. Close that browser window and it is gone. Unlock
      > the window you will actually use, and do not close it.

### Reset, then claim, then warm up — in that order

- [ ] Sidebar → **Reset demo** → **Yes, reset**. This deletes all sightings, incidents and
      matches, and **keeps the three cameras and their tokens**. The page reloads.
- [ ] On each phone: open `http://<IP>:3000/camera`.
      - Confirm the header shows green **● JS ready**. Red means the page did not hydrate —
        you are on the dev build or the network is failing. Fix it now, not on stage.
      - Paste the token → **Claim this camera**.
      - **Use my GPS location** → check the accuracy readout. If the fix is bad or the venue
        is indoors, type the surveyed junction coordinates into the **Latitude / Longitude**
        boxes by hand — that fallback exists for exactly this. Then **Save position and
        continue**.
      - **Start streaming.**
- [ ] **Check each phone is actually sending, on the phone itself:** `Frames sent` climbing
      and `Last ack` under a couple of seconds. That is the reliable test.

      > ⚠️ **A grey pin on `/map` does NOT mean the phone is dead.** A pin turns green only
      > when a *sighting* arrives from that camera in the last 30 seconds — that is, when the
      > AI actually detected a vehicle. An empty street produces frames with zero detections
      > and the pin stays grey, which is correct behaviour. Right after a reset every pin is
      > grey, because the page reloaded and nothing has been seen yet. Do not burn setup time
      > "fixing" this.

- [ ] **Warm-up pass:** Saad rides past all three cameras once, **wearing a helmet**. This
      proves detection is alive and seeds harmless sightings without opening an incident —
      and watch the pins go green as he passes each one. **That is the pin test.**
- [ ] Check `http://<IP>:8000/api/frames/stats` — `dropped` and `failed` should be **0**.
      A non-zero `dropped` means the AI is falling behind; slow the passes down. (Measured
      headroom: this laptop sustains ~0.72 frames/sec through the full pipeline and three
      phones at full rate ask for ~1.5. It sheds frames rather than dying, but do not give
      it more work than it needs — see `docs/STATS.md` §2.)
- [ ] Sidebar → **Reset demo** one more time **only if the warm-up opened an incident**
      (i.e. the helmet was not detected). Otherwise **leave it.**

      > 🔑 **The warm-up sightings ARE the candidate pool.** When the violation opens an
      > incident in segment 4, matching searches the sightings already in the database — and
      > right now those are exactly the warm-up vehicles. Reset after the warm-up and segment
      > 6's candidate list is **empty**. An empty incident feed is the right starting state;
      > an empty *sightings* table is not.
- [ ] Laptop on the projector. Browser at ~110–125% zoom. Bookmarks bar hidden. Feed page
      (`/incidents`) open, sidebar dot **● live** and green.

### Fallback kit — have this ready even if everything is working

- [ ] Folder of saved JPEG frames from a real rehearsal ride, one folder per camera, e.g.
      `d:\Daniyal Files\Traffic_Trace\demo_frames\cam1\`. If you never captured these,
      capture them at the dress rehearsal — you cannot make them on stage.
- [ ] The replay command already typed into a **third PowerShell window**, ready to run
      with one Enter. See Part 4.

---

## Part 2 — The seven minutes, segment by segment

| # | Time | Length | Who | What happens |
|---|---|---|---|---|
| 1 | 0:00 – 0:40 | 40 s | Daniyal | Hook — the gap |
| 2 | 0:40 – 1:05 | 25 s | Saad | The one line + what they are about to see |
| 3 | 1:05 – 1:40 | 35 s | Both | Register a phone as Camera 1, live |
| 4 | 1:40 – 2:25 | 45 s | Saad rides | The violation pass |
| 5 | 2:25 – 2:45 | 20 s | Daniyal | The incident appears in the feed |
| 6 | 2:45 – 3:45 | 60 s | Saad | Open review — evidence, candidates, score bars |
| 7 | 3:45 – 4:40 | 55 s | Saad rides | Reappearance at Camera 3 — the watchlist alert |
| 8 | 4:40 – 5:10 | 30 s | Daniyal | Confirm — the human in the loop |
| 9 | 5:10 – 5:55 | 45 s | Daniyal | The journey animates |
| 10 | 5:55 – 6:25 | 30 s | Daniyal | Case file, SHA-256, 48-hour retention |
| 11 | 6:25 – 7:00 | 35 s | Daniyal | Close |
| | | **420 s = 7:00** | | |

> ### ⚠️ The reappearance MUST happen before the confirm. This is not a style choice.
>
> The watchlist only checks new sightings against incidents whose status is **`open`**
> (`get_open_for_watchlist` filters on `WHERE i.status = 'open'`). The first **Confirm** on
> an incident sets its status to `confirmed` — so from that click onwards, that incident is
> no longer on the watchlist and **no reappearance toast will ever fire for it.**
>
> Confirm first and segment 7 silently does nothing, with no error anywhere. Ride first,
> confirm second, and both work. If you rehearse the order wrong once, you will lose the
> single best moment in the demo on stage.

---

### 1 · 0:00 – 0:40 — The hook (Daniyal)

*Screen: the incident feed, empty. Sidebar dot green.*

> **Daniyal:** "Every automated traffic system starts with the same question — what is the
> number plate. If it can't read one, the case is over before it starts.
>
> Now think about a motorcycle rider with no helmet, on a bike with no plate, or a bent
> plate, or a plate wrapped in cloth. The camera sees the violation perfectly. It just
> can't say who. And a rider who has already decided to break one rule has a ten-second,
> zero-cost way to break the rest of them.
>
> So we built the system that works when the plate does not."

---

### 2 · 0:40 – 1:05 — The one line (Saad)

> **Saad:** "The idea is one sentence. **When the plate cannot be read, the vehicle itself
> becomes the plate.**
>
> Every vehicle that passes every one of our cameras gets a visual fingerprint and gets
> stored — not just the offenders. Only a violation opens a case. And when a case opens,
> we don't ask what the plate was. We ask where else that exact vehicle has been seen.
>
> Three phones. One laptop. No internet in this room. Here it is running."

---

### 3 · 1:05 – 1:40 — Register a phone as a camera (Saad on the phone, Daniyal narrating)

**Clicks:** on the phone, if you re-registered for effect — `/camera` → paste token →
**Claim this camera** → **Use my GPS location** → **Save position and continue** →
**Start streaming.** On the laptop, switch to **`/map`**.

> **Daniyal:** "A camera in this system is anything that can post a picture with a token.
> Saad is holding one now. He pastes the camera's secret, the phone reads its own GPS, and
> that position is what the physics engine will use in about ninety seconds."

*Point at the map.*

> **Daniyal:** "Three cameras, three fixed positions. Every vehicle passing any of them is
> being fingerprinted and stored — including the ones doing nothing wrong. That is the part
> that makes the rest possible."

> **A pin goes green when that camera has seen a vehicle in the last 30 seconds, and fades
> back to grey when the road is quiet.** So do not promise "three green pins" — say "watch
> that pin light up as he passes it", which is what actually happens and is a better moment
> anyway. Grey pins on a quiet street are correct, not broken.

> **If it is already claimed and you are short of time:** skip the claim and just show the
> map. Saying "these were registered in ninety seconds each" is enough. Never burn stage time
> typing a token.

---

### 4 · 1:40 – 2:25 — The violation pass (Saad rides)

**Screen: switch back to `/incidents`.**

Saad rides past Camera 1 **without a helmet**, once, cleanly, at walking-to-slow speed.
**One pass. Do not loop back and forth** — repeated frames of the same vehicle crowd the
candidate list.

**Say this while the frame uploads and the AI runs — this is the longest wait in the demo:**

> **Daniyal:** "What is happening in the two seconds it takes: the frame arrives, a
> detector finds every vehicle in it, a second model checks each rider for a helmet, and
> every vehicle in that frame — offender or not — gets turned into 512 numbers describing
> how it looks, plus a colour histogram. That is the fingerprint. It is running on this
> laptop's CPU. There is no GPU in this room and no server anywhere."

> **Saad, from the phone:** "Frames sent counter is climbing. Zero failed."

---

### 5 · 2:25 – 2:45 — The incident appears (Daniyal)

The card appears in the feed on its own, highlighted amber. Do not click anything yet —
**let the judges see it arrive by itself**. Point at it.

> **Daniyal:** "There. Nobody pressed anything. That arrived over a live socket the moment
> the AI finished.
>
> And read the badge — **UNREADABLE, fingerprint mode**. We *did* try to read the plate
> first; we run a plate reader on every violation. It failed, which is exactly the case
> every other system gives up on. That badge is the whole product."

---

### 6 · 2:45 – 3:45 — The review screen (click, then Saad talks)

**Click the incident card.** The review screen opens: violation crop on the left, candidate
sightings on the right, each with a score and four bars.

> **Daniyal:** "This is the officer's screen. On the left, the offence. On the right, every
> sighting from our cameras that could possibly be the same vehicle."

> **Saad:** "'Could possibly' is doing real work there. Before we compare a single pixel we
> ask a physics question. This happened at Camera 1 at [time]. Camera 3 is 1.6 kilometres
> away. At our assumed maximum of 60 km/h that is at least 67 seconds of travel — so
> anything at Camera 3 inside 67 seconds of that time is *physically impossible*, and it is
> thrown out before the AI ever sees it. That one rule removes the overwhelming majority of
> the database instantly, and it removes exactly the coincidences that fool vision models
> hardest — an identical-looking bike somewhere it could never have been.
>
> What survives gets scored on four signals at once." *(point at the bars)* "Space-time,
> weighted 0.35. Colour histogram, 0.30. Then the two deep-learning embeddings — the vehicle
> at 0.20 and the rider at 0.15.
>
> Add those last two up: **both neural networks together carry 0.35 — exactly the same as
> physics on its own.** We did that on purpose, and I'll tell you why in a minute. It's the
> most interesting number we measured."

**Filler if the candidates are slow to render:** "Matching already ran, at the moment the
incident opened — the officer never waits on a spinner. This screen is one request."

> **At the 45-second mark of this segment, Saad hands the phone to someone and starts moving
> to Camera 3.** He needs to be riding by 3:45. **Do not touch Confirm yet** — see the
> warning above the segment table.

---

### 7 · 3:45 – 4:40 — The reappearance (Saad rides, Daniyal watches)

**Leave the review screen open.** The incident is still `open`, which is the only reason
this works. Saad rides past **Camera 3**.

**Say this while he rides — do not stare at the screen in silence:**

> **Daniyal:** "Here is the part that changes what this is for. That incident is still open.
> Every single new sighting at every camera — every ordinary vehicle, one after another — is
> being checked against the open cases, continuously. Because a vehicle that fled a
> violation at one camera is just an ordinary passing vehicle by the time it reaches the
> next one. Nothing would ever flag it unless you checked all of them."

**The amber toast fires bottom-right: "Possible reappearance".** Point at it before clicking.

> **Daniyal:** "There. Camera 3. That toast follows the officer onto whatever page he is
> looking at, because an alert that only appears on one screen is an alert you miss."

**Click the toast** → it opens the review screen, with the Camera 3 sighting now in the
candidate list. **Leave it there — you confirm in the next segment.**

> **If the toast does not fire within ~20 seconds:** do not wait, and **do not claim the hit
> was stored anyway** — a reappearance is only written to the case when it scores at or above
> **0.6**, and below that nothing is saved. Say instead: *"the check runs against every open
> case on every single sighting; this one didn't clear our alert threshold, and I'd rather
> show you a threshold that holds than one tuned for a demo"* — then click **Incidents → the
> incident** and talk over the candidate list you already have. It is still an honest,
> complete story: the journey and the case file both work without this hop.

---

### 8 · 4:40 – 5:10 — Confirm (Daniyal)

You are on the review screen with two things worth confirming: the earlier sighting the
match engine proposed when the incident opened, and the Camera 3 reappearance. **Confirm
both** — that is what makes the journey three stops instead of two.

If an obviously wrong candidate is sitting near the top, **reject it first, out loud** — it
is a stronger moment than pretending the ranking is perfect.

> **Daniyal:** "Here is the officer rejecting one the system liked." *(click Reject)* "And
> here are the two that are actually the same bike." *(click Confirm, Confirm)*
>
> "Those clicks are not decoration. Nothing in this system is ever auto-confirmed. We are
> proposing a penalty against someone who by definition cannot be identified by plate —
> anything automatic at the end of that chain would be unacceptable, so there is nothing
> automatic at the end of that chain. The keyboard shortcuts are `c` and `r`, because an
> officer reviewing twenty of these should not need a mouse."

> **If Confirm appears to do nothing:** the officer PIN is not unlocked in this browser
> window. Sidebar → **4321** → **Unlock**. Cover it with the line in Part 5 — it turns the
> mistake into a feature.

---

### 9 · 5:10 – 5:55 — The journey (Daniyal)

**Click `Journeys` in the sidebar.** Pick the incident if it is not already selected. The
route draws itself hop by hop.

*Say nothing for the first two seconds. Let it draw.*

> **Daniyal:** "Every one of those hops exists because a human said yes.
>
> Straight lines, not roads — deliberately. We know this vehicle was at that camera and
> then at that one. We do **not** know which street it took, so we do not draw one. Each hop
> carries its own distance, its own time gap, and its own confidence.
>
> And notice what this is: a route for a vehicle we cannot name, cannot look up, and have no
> registration for."

> **Stops are ordered by capture time, not by when they were confirmed.** If a warm-up
> sighting was captured *before* the violation, it is drawn first and the violation is stop
> two. That is correct and it is worth saying out loud if a judge notices — the route is the
> vehicle's timeline, not our discovery order.

---

### 10 · 5:55 – 6:25 — Evidence and privacy (Daniyal)

**Click `Case file →`** at the top right of the review screen.

> **Daniyal:** "One click, and this is a court-style case file — print it straight to PDF,
> no internet, no library. Every photograph prints its **SHA-256 hash** beside it, and the
> file on disk is *named* by that hash. Re-hash the image and you can prove it was not
> altered between the roadside and the courtroom.
>
> Section five states the limits in writing: candidates were proposed by software, **every
> match was confirmed by a human**, there is no facial recognition anywhere in this system,
> and any sighting that never became evidence is deleted after 48 hours by a job that is
> running on this laptop right now."

---

### 11 · 6:25 – 7:00 — Close (Daniyal)

> **Daniyal:** "Everything you just saw ran on one laptop, on CPU, with no internet, on
> three phones we carried in a bag.
>
> And nothing about it is phone-specific. A camera here is anything that can post a JPEG
> with a token — a CCTV camera on a pole, a dashcam, a recorded file. Which matters, because
> the expensive part of deploying this is already paid for: those e-challan cameras are
> already up, already watching, and already throwing away every vehicle whose plate they
> could not read.
>
> A number plate is the one part of a vehicle that comes off with a screwdriver. We stopped
> depending on it."

*Hand back to the deck, slide 4.*

---

## Part 3 — What to say while things load

Print this list. Someone should be able to read one aloud without thinking.

| Waiting on | Say this |
|---|---|
| The AI processing a frame (~1–2 s) | "Detection, helmet check, and a 512-number fingerprint for every vehicle in the frame — on CPU, no GPU." |
| The incident card | "It will arrive on its own. Nothing on this screen polls; it is a live socket." |
| Candidates rendering | "Matching already ran when the incident opened. The officer never waits for it." |
| The map or tiles | "These map tiles are cached on disk. There is no internet in this room — that was not optional, it was a requirement." |
| The journey animating | *(say nothing for two seconds, then)* "Every hop exists because a human confirmed it." |
| The watchlist toast | "Every new sighting at every camera is being checked against the open cases, right now." |
| Anything at all, unexpectedly | "While that finishes — the thing worth knowing here is that our two neural networks together carry no more weight than the physics does, and I'll show you the measurement that made us do that." |

**Never say:** "it's usually faster than this", "it worked in rehearsal", "hmm", or
"that's weird". Narrate what the system is doing, not what it is failing to do.

---

## Part 4 — The fallback switch

### The sentence

The moment you decide to switch — say it plainly, once, without apologising, and keep
moving:

> **"We're going to run this on recorded footage instead — this is the same pipeline
> running on this morning's recording, frame for frame. Nothing behind it changes."**

That is true. `POST /api/frames` cannot tell a phone from a replay: the camera is identified
by the `X-Camera-Token` header and nothing else. Say it with a straight back — judges
respect a prepared fallback far more than a phone that works.

**Decide by 30 seconds.** If the incident has not appeared 30 seconds after the pass, switch.
Do not try the pass a third time.

### Option A — `tools/replay.py` (Saad's, delivered and tested)

> ✅ **Verified end to end on 29 Aug.** Rehearse it once in Phase 19 against your own
> recording, and this is the command you type on stage.

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

### Option B — saved frames over `curl` (works today, with the endpoint exactly as built)

Have this pre-typed in a third PowerShell window. One Enter and it runs.

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

It posts to `127.0.0.1`, **so it does not touch the network at all** — this fallback
survives the hotspot dying completely.

> ### The `-F "ts=..."` is the part that makes this work at all
>
> `ts` is the **capture** time and it is what the space-time gate reasons about. Omit it and
> the endpoint stamps every frame with its arrival time — so all three cameras' frames land
> within seconds of each other, the gate correctly rules that no vehicle could have covered
> 1.4 km in four seconds, and you get an incident with **zero candidates and no journey**.
> The fallback would appear to run perfectly and produce nothing.
>
> The offsets above (−4 / −2 / 0 minutes) put ~120 s between consecutive cameras, comfortably
> over the 52–96 s the gate demands at the seeded spacing. Camera 2 goes **first** so its
> sightings already exist when the Camera 1 violation opens the incident; Camera 3 goes last
> so it arrives as a watchlist reappearance, exactly like the live run.
>
> **Order matters here too:** run all three blocks *before* confirming anything. The first
> confirm closes the incident to the watchlist (see the warning in Part 2).

> The 400 ms sleep is not decoration either. Fire every frame at once and the ingest queue
> (bounded at **8**) starts **evicting the oldest queued frame** to make room — during a replay
> that is the beginning of the ride, which is exactly where the violation pass usually is.

### Option C — the cold fallback (last resort, ~10 seconds to reach)

If the pipeline itself is down (`/api/health` says `pipeline.real: false`) — **do not run
the stub in front of judges.** Go to a case file you exported and saved as PDF the night
before, and walk through it:

> "Our AI process isn't loading on this machine right now, so rather than show you something
> fake, here is a case this system produced this morning — same screens, same evidence,
> same hashes."

**Prepare for this the night before:** export one full case file to PDF and save it to the
desktop, and screenshot the journey map with a completed route. Two files. If you never need
them, you lost five minutes.

---

## Part 5 — When something breaks

### A phone dies or the camera page freezes

Saad's spare phone is already claimed to the same camera and in his pocket, screen on.
**A token identifies a camera, not a handset** — a second phone with the same token simply
becomes that camera. Swap it onto the tripod and carry on.

> **Daniyal, covering:** "Saad is swapping the handset — the camera identity lives in the
> token, not the phone, so it just picks up where the other one left off."

If the page is up but the counters have stopped: on the phone, **Stop** then **Start
streaming**. If that fails, reload the page — the token is in `localStorage`, so it will not
ask for the secret again.

### The network drops

Symptom: the sidebar dot turns **red / offline**, or the phone's "Last ack" climbs past a
few seconds.

1. **Say the true thing, immediately:** *"The dashboard just lost its link — that dot is the
   connection, not the system. The cameras keep capturing and retrying; this is what it looks
   like when the network wobbles, and it recovers on its own."* The WebSocket reconnects with
   backoff and the phone retries with backoff. Often it comes back while you are talking.
2. If it does not come back in ~10 seconds: reload the laptop page. The dashboard reads
   durable state over REST and uses the socket only to know *when* to refresh, so a reload
   loses nothing.
3. If the hotspot is gone entirely: go to **Option B** above. It posts to `127.0.0.1` and
   needs no network at all. The demo continues on one laptop, offline, which is a story in
   itself — say so.

### The AI is slow

Symptom: `Server queue` climbing on the phone, or `dropped` non-zero at
`/api/frames/stats`.

- **Stop moving.** Extra passes make it worse. One vehicle, one pass.
- Have Saad **Stop** streaming on the two cameras you are not using at that instant. Three
  phones streaming into a CPU pipeline is three times the work.
- Cover it honestly: *"That queue number is the system protecting itself — under load it
  drops frames rather than memory, so it degrades instead of dying. On a real deployment this
  is a GPU box, not a laptop."*
- Do **not** kill and restart the API to "clear it". Restarting loses the queue, the
  WebSocket, and about forty seconds you do not have.

### Nothing is detected on the pass

- Ride past again, **slower**, and closer to the camera. Once.
- Check the phone shows **● BURST** as the vehicle crosses — if it never bursts, the motion
  detector is not seeing the pass and the framing is wrong.
- If two passes fail: switch to the fallback. Do not attempt a third.

### The Confirm button does nothing

The officer PIN is not unlocked in this browser window (or the window was closed and
`sessionStorage` was cleared). Sidebar → enter **4321** → **Unlock**. Cover it with:
*"Confirming is PIN-gated — the read-only screens are open so they can be projected, but
anything that changes a case needs an officer."* This turns the mistake into a feature, which
is why it is worth knowing.

### You are running out of time

Cut in this order:
1. Segment 3 (registering the camera) — show the map instead.
2. Segment 10 (case file) — mention SHA-256 in one line during segment 9.
3. Segment 8's reject-then-confirm — just confirm.

**Never cut segment 7 (the reappearance) or segment 9 (the journey).** Those two are why the
project exists. And never reorder them so a confirm lands before the reappearance ride — the
watchlist stops watching an incident the moment it is confirmed.
