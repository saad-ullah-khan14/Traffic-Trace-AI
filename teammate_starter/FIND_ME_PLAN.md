# "Find Me" — search every camera for a vehicle or a person

**Build plan. Written 4 Sep 2026.**
Read `HANDOFF.md` §4 and `PROBLEMS.txt` first — every number in this document
comes from them, and the honest limits of this feature come from them too.

---

## 1. What the officer does

A motorcycle is stolen. A child is taken from a street on the back of a bike.
The officer has one photograph — of the bike, or of the person.

They open **Find Me**, upload that photograph, optionally narrow it ("motorcycle,
last four hours, these two cameras"), and get back a short ranked list of
sightings from every camera in the system. For each one: the crop, which camera,
what time, and the frame it came from. They confirm the ones that are the same
vehicle or person, and those confirmed hits draw a route on the map — exactly the
journey view that already exists.

That is the whole feature.

---

## 2. The one thing that makes this feasible

**You do not search video. You search the fingerprints that were already
extracted while the video was being ingested.**

Every frame that has ever reached the API has already been through
`process_frame`: detected, cropped, embedded, and written to the `sightings`
table with its camera, its timestamp and its 512-dimension CLIP vector. That
table IS the search index. It exists, it is populated, and it is queryable today.

Searching recorded video frame by frame at query time would take minutes per
search and would re-do work that was already done at 1 fps during ingest. Nobody
should build that.

Recording the raw frames is still worth doing — but for **showing the officer
where the hit came from**, not for searching. That is why it is Phase 4 here and
not Phase 1. The search works before a single frame is recorded.

---

## 3. What already exists — do not rebuild any of this

This is the most important section in the document. Roughly 70% of "Find Me" is
already in the repo:

| You need | It already exists | Where |
|---|---|---|
| A searchable index of everything seen | `sightings` table: `veh_emb`, `rider_emb`, `attrs`, `ts`, `camera_id`, `crop_path`, `vehicle_type`, `confidence` | `contracts/schema.sql` |
| Turn an uploaded photo into a vector | `process_frame(image_bytes, camera_id, ts)` — detects, crops, embeds, returns `veh_emb` + `rider_emb` + `attrs` | `pipeline/orchestrator.py`, called via `app/services/pipeline_client.py` |
| Rank candidates by appearance | `rank_by_cosine(query_embedding, candidates, top_k, embedding_field)` — **already takes `embedding_field`, so it can rank on `rider_emb` instead of `veh_emb` with no changes at all** | `api/app/services/matching.py` |
| Narrow by time / camera before ranking | the same SQL-gates-then-numpy-ranks pattern the matcher uses | `api/app/db/queries/sightings.py` |
| Review one candidate at a time, confirm or reject | the whole review screen, including the top-5 shortlist and "candidates at an already-identified camera leave the queue" | `dashboard/src/app/incidents/[id]/page.tsx` |
| Draw confirmed hits as a route on a map | journeys service + `JourneyMap` | `api/app/services/journeys.py`, `dashboard/src/components/JourneyMap.tsx` |
| Officer PIN gate | `require_pin` dependency | `api/app/core/security.py` |

**The genuinely new code is: one endpoint, one page, and a frame recorder.**

---

## 4. What this feature can and cannot do

Say this out loud before building, because the alternative is discovering it on
stage.

**It ranks. It does not decide.** Measured on this project's own labelled data,
24 officer-labelled cross-camera pairs:

```
rank-1    3/3      the true match ranked FIRST in every incident
margin   -0.077    confirmed 0.853-0.951, rejected 0.730-0.930 - overlapping
```

The order is trustworthy. The absolute score is not — any two motorcycles land
between 0.73 and 0.96 because CLIP encodes *category*, not *identity*. So:

- Show a **ranked shortlist**, never a "match found" verdict.
- Never auto-confirm. The officer decides, as everywhere else in this product.
- Do **not** put a confidence threshold on the results. That has been tried
  twice here and retired both times; see `PROBLEMS.txt` Part 1 item 5.

**Person search should be better than vehicle search, and the schema already
supports it.** Commuter motorcycles are near-identical; people are not. `rider_emb`
is stored separately for every sighting, so "find this person" ranks on
`rider_emb` and "find this bike" ranks on `veh_emb`. Offer both as a toggle.

**The domain gap is real and unmeasured here.** The officer's uploaded photo is
usually a clean, well-lit picture. The gallery is blurry 100-200 px street crops.
Matching across that gap is a known-hard problem in re-identification, and this
project has never measured it. Phase 5 exists to find out before anyone promises
a number.

---

## 5. The phases

Each phase ships something that works on its own. Do not start a phase before the
one above it is verified.

---

### Phase 0 — Decide the question, and how it will be judged (half a day, no code)

Write down, before any code:

- **What is searched**: vehicle (`veh_emb`) or person (`rider_emb`) — the officer
  picks, and the default is vehicle.
- **What the officer may narrow by**: time window, camera, vehicle type. All of
  these are exact SQL filters and they narrow honestly, unlike the score.
- **What "good" means**: given a crop of a known vehicle as the query, does the
  system rank that vehicle's *other* sightings in the top 5? That is the metric.
  It is the same rank-1 / margin discipline as `api/scripts/bench_matcher.py`.

**Done when**: the success metric is written in this file and agreed, before the
endpoint exists. Every wrong turn on this project came from measuring after.

---

### Phase 1 — The search endpoint (1-2 days)

`POST /api/search` — multipart: an image, plus optional filters.

```
image        the photo to find
mode         "vehicle" | "person"     (default vehicle)
from_ts      optional
to_ts        optional
camera_ids   optional, repeated
limit        default 20
```

Flow, in the order the project already uses everywhere else — **SQL narrows,
numpy ranks**:

1. Run the uploaded image through `process_frame`. It returns detections with
   `veh_emb`, `rider_emb`, `attrs`.
   - **No detection** → return a clear error: *"No vehicle found in that photo.
     Crop it closer to the bike."* Do not fall back to embedding the whole
     photograph; a picture of a street is not a query.
   - **More than one detection** → return them and let the officer pick which one
     they mean, using the same crops the system would store. Do not guess.
2. Pull candidate sightings with a plain SQL filter on `ts`, `camera_id`,
   `vehicle_type`. Nothing visual yet.
3. `rank_by_cosine(query_emb, candidates, top_k=limit, embedding_field=...)`
   — `"veh_emb"` or `"rider_emb"` depending on `mode`.
4. Return them best-first with camera name, timestamp, crop URL and score.

Layering rules that apply (see `PROBLEMS.txt` Part 5): the route contains no SQL,
the service imports no `fastapi`, and only `pipeline_client.py` touches
`pipeline/`.

**Done when**: `curl` with a crop taken straight out of `evidence/` returns that
same sighting as rank 1. If a photo of a vehicle cannot find *itself*, nothing
else in this feature will work.

---

### Phase 2 — The Find Me screen (1-2 days)

A new page, `/find`, in the dashboard. Behind the officer PIN.

- Upload (file picker and drag-drop), a vehicle/person toggle, and the optional
  time and camera filters.
- Results as the **existing review pattern**: one big comparison at a time — the
  uploaded photo on the left, one candidate on the right, *Same vehicle* /
  *Not the same* — with the filmstrip beneath.
- **Reuse the rules already built and measured**, do not invent new ones:
  - top 5 shown, the rest behind *show the other N*
  - once a camera is confirmed, its remaining candidates leave the queue
  - nothing is hidden permanently

Copy the interaction from `dashboard/src/app/incidents/[id]/page.tsx` rather than
writing a second, divergent review UI.

**Done when**: an officer can upload a crop and reach a confirmed hit without
touching the keyboard except to type the PIN.

---

### Phase 3 — Where it was found: map and timeline (half a day)

Confirmed hits are already exactly what the journey builder consumes: a set of
sightings with camera, position and time.

- After the first confirm, show the same map component the incident view uses.
- Order hits by time, draw the route, show each hop's distance and time gap.
- **Use the reachability gate as a sanity check, not a filter.** Flag a hop as
  implausible if it would need more than `MAX_PLAUSIBLE_KMH`, but still show it —
  the officer is searching, not prosecuting, and a wrong-looking hop is
  information.

**Done when**: two confirmed hits at different cameras draw a line on the map with
the correct distance and elapsed time.

---

### Phase 4 — Record the frames (1 day, and this is where the disk risk lives)

Only now, and only for context — the search does not need it.

- Save every ingested frame to `evidence/frames/<camera>/<YYYYMMDD>/<HHMMSS>.jpg`.
  The frame bytes are already in hand in `ingest_frame`; this is a write, not a
  re-encode.
- Store the path on the sighting so a result can show the **whole scene**, not
  just the crop.
- Add "see the frame" to the Find Me result and to the incident view.

**Three hard requirements, all of them learned the hard way here:**

1. **Write to `D:`, never `C:`.** `EVIDENCE_DIR` is already `../evidence`, which
   lives beside the project on D:. C: has been down to 0.24 GB and at that point
   the models stop loading entirely — see `PROBLEMS.txt` PROBLEM 11.
2. **A retention policy, written before the first frame is saved.** Measured:
   frames are 64-115 KB. At three cameras during an active session this is
   roughly 60-700 MB per hour depending on how hard the phones are bursting.
   Delete frames older than N hours on a schedule, and make N a constant with the
   measurement written beside it.
3. **A disk guard.** If free space on the target drive drops below a floor, stop
   recording and log a warning — never let frame recording be the thing that
   takes the demo down.

**Done when**: a result can show the full frame it came from, and a day of running
does not move the free-space number in a way that worries anyone.

---

### Phase 5 — Measure it (half a day, and skipping it makes everything above a guess)

Build the search benchmark the same way `api/scripts/bench_matcher.py` was built,
reusing `labelset/`:

- For each labelled sighting, use its crop as the query.
- Search the rest of the table.
- Report **rank-1** (are the officer-confirmed siblings first?) and how deep in
  the list the last true sibling appears.
- Report **ms per search** as the table grows — 100, 1000, 10000 sightings.

Two things this will tell you, both of which someone will otherwise assume:

- Whether the **domain gap** (clean query photo vs blurry gallery crop) destroys
  the ranking. Test it deliberately: query with a phone photo of a bike, not just
  with a crop already in the database.
- When numpy stops being enough. A few thousand 512-d vectors is microseconds; a
  few million is not. **Do not add an index before this number says so** — that is
  the point at which pgvector or FAISS becomes worth its cost, and not a moment
  earlier.

---

### Phase 6 — Audit trail (half a day)

This feature searches for people. That carries a requirement, and it also
strengthens the pitch rather than weakening it:

- Every search is behind the officer PIN — reuse `require_pin`.
- Every search writes a row: who, when, which image (hash), which filters, how
  many results, and what was confirmed.
- The uploaded query image is stored with its SHA-256, like `crop_hash` already
  does for evidence.

**Done when**: "who searched for what, and when" can be answered from the
database without reading a log file.

---

## 6. Effort and order

| Phase | What | Effort | Blocks |
|---|---|---|---|
| 0 | Define the question and the metric | half a day | everything |
| 1 | Search endpoint | 1-2 days | 2, 5 |
| 2 | Find Me screen | 1-2 days | 3 |
| 3 | Map and timeline of hits | half a day | — |
| 4 | Frame recording + retention + disk guard | 1 day | — |
| 5 | Search benchmark | half a day | needs 1 |
| 6 | Audit trail | half a day | — |

**Start at 0, then 1. Phases 4 and 6 can run in parallel with 2 and 3** — they
touch different files.

Shortest path to something demonstrable: **0 → 1 → 2**. That is a working Find Me
in about three days, with no new storage and no new model.

---

## 7. Risks, each with the measurement behind it

**The ranking may not survive the domain gap.** A clean uploaded photo against
blurry street crops is a harder problem than crop-against-crop, and this project
has never measured it. Phase 5 measures it. If it fails, the honest answer is the
one the product already makes everywhere: show the top few, let the officer
decide, and say plainly that the system narrows rather than identifies.

**Detection quality caps everything.** Measured: bikes below ~96 px are dropped,
and re-photographed screen footage produces zero usable detections at any zoom
(`PROBLEMS.txt` PROBLEM 1). Find Me can only find what was detected and stored in
the first place. If the cameras did not see it, no search will conjure it.

**Disk.** See Phase 4. C: has already hit 0.24 GB once and took the models down
with it.

**Search latency as the table grows.** Fine today, unmeasured at scale. Phase 5
says when to care. Do not pre-optimise it.

---

## 8. Rules that must not be broken

These are not style preferences; each one was paid for.

1. **Never measure on synthetic input.** Not identical images, not random
   vectors. Real crops of the same bike from two cameras score 0.52-0.55; the
   same image posted twice scores 0.92. Three wrong decisions came from this.
2. **A count is not a check.** Render the thing and look at it. "0 detected" was
   logged hundreds of times and could not distinguish an empty road from a black
   frame from a sideways one.
3. **Never put an absolute threshold on the similarity score.** It has been tried
   and retired twice. Rank, then cut by rank.
4. **Nothing is auto-confirmed, ever.** The officer decides. That claim is made
   explicitly in the pitch and it is the reason this product is defensible.
5. **`pipeline/` never imports from `api/`.** `pipeline_client.py` is the only
   crossing point. A route with SQL in it is a bug; a service importing `fastapi`
   is a bug.
6. **Embeddings stay `float4[]` + numpy cosine, 512 dimensions.** A model with a
   different dimension is a schema migration and invalidates every stored vector.
   Flag it before writing code.
7. **Write the measurement next to the constant.** Every tuned number in this
   repo carries the run that justified it. Keep that habit; it is the only reason
   this project can be handed over at all.
