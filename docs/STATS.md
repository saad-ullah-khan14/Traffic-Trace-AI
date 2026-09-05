# Measured Performance — Traffic_Trace

> Every number below was produced by running the system on 24 Aug 2026, not copied
> from an earlier phase log. Where a re-run disagreed with `PROGRESS.md`, the new
> number is the one recorded here and the difference is explained.

## The hardware everything was measured on

| | |
|---|---|
| CPU | Intel Core i5-4460 @ 3.20 GHz — **4 cores, 4 threads**, no hyper-threading |
| RAM | 16 GB |
| GPU | GTX 750 Ti — **unused**. Too old for the CUDA builds of torch we need, so every model runs on CPU |
| OS | Windows 11 Pro 24H2 (build 26100) |
| Python | 3.12.9, `api/.venv` |
| Database | Native PostgreSQL 18.4, local connection to 127.0.0.1 |
| Disk | Local SSD; database and evidence folder both on `D:` |

This is a 2014 desktop CPU. It is deliberately the number we quote: if the demo
runs here, it runs anywhere.

---

## 1. Matching latency

The hot path: a violation opens an incident, the SQL space-time gate narrows the
whole sightings table down to at most 500 candidates, numpy ranks those by cosine,
and the survivors are hydrated with their crops and camera details.

**Command**

```powershell
cd "d:\Daniyal Files\Traffic_Trace\api"
.\.venv\Scripts\python.exe -m scripts.bench_matching
.\.venv\Scripts\python.exe -m scripts.bench_matching --rows 20000
```

The script inserts synthetic normalized embeddings, times 20 runs of each stage,
and deletes its own rows afterwards. The incident is anchored mid-window so the
gate scans both backwards and forwards in time — anchoring at `now()` leaves the
forward half empty and understates the work.

**5,003 sightings in the table, 500 candidates survive the gate**

| Stage | Median | Min | Max |
|---|---|---|---|
| SQL space-time gate | **36.50 ms** | 35.46 ms | 40.50 ms |
| numpy cosine top-5 | **0.98 ms** | 0.63 ms | 1.19 ms |
| gate + rank | 37.51 ms | 36.25 ms | 41.69 ms |
| **`find_candidates` end to end** | **37.78 ms** | 37.20 ms | 40.21 ms |

Under the 50 ms budget agreed in Phase 3. **PASS.**

**20,003 sightings in the table, still 500 candidates survive the gate**

| Stage | Median | Min | Max |
|---|---|---|---|
| SQL space-time gate | **59.72 ms** | 57.75 ms | 62.28 ms |
| numpy cosine top-5 | **0.88 ms** | 0.65 ms | 1.19 ms |
| gate + rank | 60.65 ms | 58.71 ms | 63.38 ms |
| **`find_candidates` end to end** | **60.96 ms** | 59.47 ms | 63.98 ms |

**Over the 50 ms budget. FAIL** — and worth stating plainly rather than burying.

**How it scales:** 4× the rows costs 1.61× the latency. Sub-linear, because the
`(camera_id, ts DESC)` index means Postgres never reads the whole table — but not
flat, because a denser table means more index entries walked before the `LIMIT`
is satisfied.

Every millisecond of that growth is in the SQL gate. The numpy ranking is
**unchanged at ~0.9 ms** between 5k and 20k rows, because the gate hands it exactly
500 candidates either way. Dropping pgvector cost us nothing measurable; the
similarity search is not the bottleneck and would not be at 100× this size.

**What this means for the demo:** the demo database will hold hundreds of
sightings, not twenty thousand. 37 ms is the number that applies. The 20k figure
answers "what happens if this runs all day", and the answer is that the gate —
not the vector search — is what needs rethinking first.

**Reconciling with PROGRESS.md:** the Phase 3 log says 37.2 ms and the post-audit
log says 43.4 ms for the same 5,000-row test. This run measured 37.78 ms. All three
sit inside the noise of a machine that is also running Postgres, so treat matching
as "≈40 ms at demo scale" rather than trusting any single decimal.

---

## 2. Inference throughput

Real street photos posted through the real endpoint with the real models loaded.
No stub anywhere — `/api/health` reported `"pipeline":{"real":true}` for the whole
run.

**Command**

```powershell
# terminal 1
cd "d:\Daniyal Files\Traffic_Trace\api"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# terminal 2 — post one frame, then poll until the worker counter moves
curl.exe -X POST http://127.0.0.1:8000/api/frames -H "X-Camera-Token: pvGlw0kKEcfR6QR6HIOHYED473NESzl-" -F "frame=@D:\Downloads\project (3)\project\test_images\street1.jpg" -F "ts=2026-08-24T00:00:00Z"
curl.exe http://127.0.0.1:8000/api/frames/stats
```

The timings below came from a throwaway script doing exactly that in a loop: POST,
then poll `/api/frames/stats` every 20 ms until `processed` increments. That
measures the **whole worker job** — decode, YOLOv8n, the helmet model, one CLIP
embedding per detection, crop write, DB inserts, watchlist, and match scoring —
not just the model call.

**One frame at a time, worker idle before each**

| Frame | Size | `POST` → 202 | Worker time |
|---|---|---|---|
| `street1.jpg` | 884 KB | 11.6 ms | 1.33 s |
| `street2.jpg` | 1103 KB | 11.6 ms | 1.82 s |
| `street3.jpg` | 875 KB | 7.0 ms | 1.79 s |
| `no_helmet_test.png` | 911 KB | 8.3 ms | 0.49 s |

Median **1.56 s per frame → 0.64 fps**.

**All four posted back to back (burst)**

| Measure | Result |
|---|---|
| 4 POSTs accepted | 105 ms total, 26 ms each |
| Worker drained 4 frames | **5.54 s → 0.72 fps sustained** |
| Dropped / failed | **0 / 0** |

**Compared to the demo's actual load:** three phones at one frame every two
seconds is **1.5 fps**. The worker sustains **0.72 fps**. The demo asks for
roughly **2.1× more than this laptop can process.**

That is not a crash, because the design already anticipated it: `POST /api/frames`
returns 202 in ~8–12 ms without waiting for inference, and the queue is bounded at
64 frames and drops rather than growing. At the numbers above, three phones
streaming flat out fill the queue in **about 82 seconds**, after which the system
keeps running and starts discarding frames.

Two things stop this being a problem in the actual demo:

1. The camera page only streams at full rate **when it detects motion**. An empty
   street posts far less often, so 1.5 fps is a peak, not an average.
2. Dropped frames cost coverage, not correctness. A dropped frame is a vehicle we
   did not fingerprint; it never corrupts a sighting that was captured.

**Where the time goes:** frame size does not predict cost — `no_helmet_test.png` is
911 KB and took 0.49 s, `street3.jpg` is 875 KB and took 1.79 s. Detection *count*
predicts it. Roughly **~0.3 s fixed** (decode + YOLO + helmet model on the full
frame) **plus ~0.15 s per detected vehicle** (one CLIP crop embedding each). A frame
with one motorcycle is fast; a frame with eight vehicles is not.

---

## 3. Detection yield on real street photos

Same run, counted straight out of Postgres before and after each frame.

| Frame | Sightings | Incidents | Matches written |
|---|---|---|---|
| `street1.jpg` | 8 | 0 | 16 |
| `street2.jpg` | 8 | 1 | 29 |
| `street3.jpg` | 6 | 3 | 76 |
| `no_helmet_test.png` | 1 | 1 | 26 |
| **Total from 4 photos** | **23** | **5** | **147** |

Four ordinary street photographs produced 23 fingerprinted vehicles and 5
no-helmet incidents. That ratio is the product's whole premise working as
intended: **every vehicle is stored, only violations open a case.** 18 of those 23
sightings were vehicles nobody had any reason to care about at the time — and they
are exactly what the system searches when a violation appears later.

**A scaling warning found by accident.** Posting the *same* four frames a second
time added 23 more sightings and 5 more incidents, but **271 more matches** — almost
double the first pass. Match volume grows with (open incidents × reachable
sightings), and both grow during a demo. Nothing was slow enough to matter over
eight frames, but this is the term that grows fastest, and Teammate 1's missing
`dedupe` is what would keep it in check.

---

## 4. Embedding quality — does the fusion actually help?

**This is the most important measurement in this document**, because the entire
product rests on recognising the same vehicle at a second camera, and Phase 7
already found that CLIP alone cannot do it.

Test images: `a1.png` / `a2.png` are two photos of one motorcycle. `b1.png` /
`b2.png` are two photos of a different motorcycle. That gives 2 same-vehicle pairs
and 4 different-vehicle pairs.

**Command**

```powershell
cd "d:\Daniyal Files\Traffic_Trace\api"
.\.venv\Scripts\python.exe -m scripts.bench_embeddings
```

`scripts/bench_embeddings.py` runs the real `process_frame` on each image, takes the
motorcycle detection, and compares every pair two ways: the raw `veh_emb` cosine,
and the full four-signal score from `pipeline.score_candidates` with
`distance_m = 1373` and `time_gap_seconds = 180` (the real Camera 1 → Camera 2 hop
from the Phase 13 journey).

### Results

| Pair | Kind | Raw CLIP cosine | Fused score | vehicle | rider | attributes | space-time |
|---|---|---|---|---|---|---|---|
| a1 ↔ a2 | **same** | 0.9332 | 0.7776 | 0.933 | 0.895 | 0.890 | 0.542 |
| a1 ↔ b1 | diff | 0.9179 | 0.7639 | 0.918 | 0.844 | 0.880 | 0.542 |
| a2 ↔ b1 | diff | 0.8825 | 0.7612 | 0.882 | 0.775 | 0.929 | 0.542 |
| b1 ↔ b2 | **same** | 0.8703 | 0.7353 | 0.870 | — | 0.870 | 0.542 |
| a2 ↔ b2 | diff | 0.8647 | 0.7161 | 0.865 | — | 0.820 | 0.542 |
| a1 ↔ b2 | diff | 0.8391 | 0.7095 | 0.839 | — | 0.818 | 0.542 |

Rows are in descending fused score. The raw-cosine ordering is **identical**.

### Does same-vehicle beat different-vehicle?

**No — not reliably, on either signal.**

The separation margin is the worst same-vehicle pair minus the best
different-vehicle pair. Positive means one threshold cleanly divides them.

| Signal | Worst same | Best different | Margin | Separates? |
|---|---|---|---|---|
| Raw `veh_emb` cosine | 0.8703 | 0.9179 | **−0.0476** | **No** |
| Full fused score | 0.7353 | 0.7639 | **−0.0286** | **No** |

The same-vehicle pair `b1 ↔ b2` is beaten by the different-vehicle pair `a1 ↔ b1`
under both. Two different motorcycles still look more alike to this system than one
motorcycle photographed twice.

### Did fusion beat the raw embedding?

**Yes, but only by narrowing the gap — it did not change a single ranking.**

- Margin improved from **−0.0476 to −0.0286**. The overlap shrank by **40%**.
- Mean same-vehicle minus mean different-vehicle: raw **+0.0257**, fused **+0.0188**.
- The rank order of all six pairs is **identical** under both signals.

So the fusion is measurably better on the metric that matters for a threshold, and
completely neutral on the metric that matters for a top-20 candidate list. On this
sample it rescales the problem rather than solving it.

### Two findings that contradict the current design rationale

**1. The colour histogram is the *worst* identity signal here, not the best.**
`matcher.py` gives it weight 0.30 — more than CLIP's 0.20 — on the stated reasoning
that it is "a stronger, non-semantic signal". Measured on these four images:

| Signal | Weight in `matcher.py` | Margin |
|---|---|---|
| rider embedding | 0.15 | **+0.051** |
| CLIP vehicle embedding | 0.20 | −0.048 |
| colour histogram | 0.30 | **−0.059** |

The single highest attribute score in the whole table, 0.929, belongs to `a2 ↔ b1`
— a **different**-vehicle pair. The histogram ranked two different bikes as the best
colour match of all six pairs.

**2. The rider embedding is the only signal that separates, and it carries the
lowest weight of the three visual ones.** Where it exists it put the same-vehicle
pair (0.895) above both different-vehicle pairs (0.844, 0.775). It is a sample of
three pairs, so this is a lead and not a conclusion — but it points the opposite
way to the current weighting, and it is cheap to test: it is one number in
`matcher.py`.

It also has an obvious failure mode, visible above. `b2.png` produced **no rider
crop**, so `b1 ↔ b2` — a genuine same-vehicle pair — lost its only working signal
and had that weight redistributed to the two that get it wrong. That is a large part
of why it scored so badly.

### The honest caveat on space-time

Space-time scored **0.542 for every pair**, because the test deliberately holds
`distance_m` and `time_gap_seconds` constant so the *visual* signals can be compared
like for like. At weight 0.35 it therefore contributed a constant offset and **zero
discrimination** in this table.

That is not how it behaves live. In the real system every candidate has its own
distance and time gap, and the signal's real job is a hard reject: anything
requiring more than 60 km/h scores 0.0 and is eliminated. This test measures what
the fusion can do *after* the space-time gate has already thrown out the impossible
— which is the correct thing to isolate, but it means the fused numbers here are
the pessimistic case, not the whole picture.

---

## 5. Storage

**Command**

```sql
-- per-column logical size, over 49 real sightings from the street photos
SELECT round(avg(pg_column_size(veh_emb))), round(avg(pg_column_size(rider_emb))),
       round(avg(pg_column_size(attrs))),   round(avg(pg_column_size(bbox))),
       round(avg(pg_column_size(sightings.*)))
FROM sightings;

-- real on-disk footprint, after: VACUUM (FULL, ANALYZE) sightings;
SELECT pg_relation_size(c.oid) heap, pg_indexes_size(c.oid) indexes,
       pg_total_relation_size(c.reltoastrelid) toast, pg_total_relation_size(c.oid) total
FROM pg_class c WHERE c.relname = 'sightings';
```

**Per sighting, logical size** (measured, 49 real sightings)

| Column | Bytes | Note |
|---|---|---|
| `veh_emb` | **2,068** | 512 × float4 + 20-byte array header |
| `rider_emb` | **2,068** when present | present on **25 of 49** rows (51%) — only motorcycles with a detected rider |
| `attrs` (jsonb) | 214 | colour name + colour histogram |
| `bbox` (jsonb) | 65 | |
| everything else | ~1,289 | ids, timestamps, crop path, crop hash, confidence |
| **whole row** | **3,636** | |

**On disk** — the table was grown to 1,003 real sightings and vacuumed, so this is
measured rather than extrapolated:

| | Bytes | Per sighting |
|---|---|---|
| Heap | 548,864 | 547 |
| Indexes (6 of them) | 81,920 | 82 |
| TOAST (where the embeddings live) | 4,128,768 | **4,116** |
| **Total** | **4,759,552 (4.54 MB)** | **4,745** |

The embeddings dominate, and they cost ~35% more on disk than their logical size:
random float32 does not compress, and a 2,068-byte value crosses TOAST's ~2,000-byte
chunk boundary, so each embedding becomes two chunks with their own tuple overhead.

**Crop files** (23 distinct crops from the four street photos)

| | |
|---|---|
| Mean | **21.0 KB** |
| Min / max | 2.6 KB / 70.6 KB |
| Total | 484 KB |

Crops are named by the SHA-256 of their contents, so identical crops share one file
automatically. Re-posting the same four frames produced 23 more sightings and
**zero** new files.

### Extrapolated to 1,000 sightings

| | |
|---|---|
| Postgres | **4.54 MB** (measured at 1,003 rows) |
| Crop files | **~21 MB** (1,000 × 21.0 KB, assuming no dedupe) |
| **Total** | **~25.5 MB** |

The crops are 4.6× the size of everything else combined. If space ever becomes the
constraint, the lever is JPEG quality on the crop, not the embedding.

---

## 6. Startup time

Both models load at import, so `uvicorn` is not ready until YOLOv8n, the helmet
model and CLIP ViT-B/32 are all in memory.

**Command** — launch uvicorn, poll `/api/health` every 50 ms, stop at the first 200:

```powershell
cd "d:\Daniyal Files\Traffic_Trace\api"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# in another shell, timed from the moment uvicorn was launched:
curl.exe http://127.0.0.1:8000/api/health
```

| Run | Time to first 200 |
|---|---|
| 1 — cold (weights not in the OS file cache) | **16.04 s** |
| 2 — warm | 10.79 s |
| 3 — warm | 10.32 s |

The response confirms the real models loaded, not the stub:

```json
{"status":"ok","db":{"ok":true,"database":"traffic_trace","version":"PostgreSQL 18.4"},
 "pipeline":{"real":true,"status":"real pipeline loaded"}}
```

**For demo day: start the API at least 20 seconds before anyone is watching.** If it
is restarted on stage after a crash, that is 10–16 seconds of dead air, and
`/api/health` is the only honest signal that it is back.

---

## What these numbers do and do not show

### What they show

- **Matching is fast enough, with room to spare, at demo scale.** 37.78 ms end to
  end against 5,000 sightings. The officer never waits for candidates, because
  matching runs the moment the incident opens, not when the review screen loads.
- **Skipping pgvector was the right call.** The numpy ranking is 0.9 ms and does not
  grow between 5k and 20k rows. All the latency, and all the growth, is in the SQL
  gate. An index would have solved a problem we do not have.
- **The API stays responsive under inference load.** POST returns 202 in 7–12 ms
  regardless of how backed up the worker is. A phone is never blocked by the model.
- **Nothing broke.** Across every frame posted in this session: 0 dropped, 0 failed.
- **The detect-and-fingerprint path genuinely works on real photographs**, not
  staged inputs. 23 vehicles and 5 real no-helmet incidents from 4 street photos.
- **Storage is a non-issue at this scale.** 25 MB per 1,000 sightings.

### What they do not show

- **They are not a benchmark of the demo.** Four photographs is not a traffic
  stream. Nothing here was measured with three phones streaming simultaneously over
  a hotspot, and that is the configuration that will actually run on stage.
- **Throughput is measured against the demo's load and comes up short.** 0.72 fps
  sustained against a 1.5 fps peak. It degrades safely by dropping frames, but "the
  laptop keeps up" is not a claim these numbers support.
- **The matching latency numbers use random embeddings.** Random vectors give ~0.0
  cosine, so the *timings* are honest — the work is identical — but the *quality* of
  a 500-candidate ranking on real data is not measured by that script.
- **The embedding test is four images.** Two vehicles, six pairs. It is enough to
  show that a problem exists — a same-vehicle pair losing to a different-vehicle
  pair is a real failure whatever the sample size — but nowhere near enough to tune
  weights on. Every claim in §4 about which signal is best needs re-testing on real
  recorded street pairs before anyone changes `matcher.py`.
- **They say nothing about accuracy end to end.** There is no precision or recall
  number here, because there is no labelled ground-truth set. We do not know how
  often the true match lands in the top 20; we only know the top *1* is often wrong.
  That is precisely why an officer confirms every match, and why the case file says
  so in writing.
- **The 20,000-row result is a warning, not a demo risk.** The demo database will
  hold hundreds of rows. But the system as built exceeds its own 50 ms budget at 20k
  sightings, and that is where the next optimisation belongs if this ever runs for
  more than an afternoon.
- **They are one machine, one afternoon.** Every figure is a median of a handful of
  runs on a shared laptop also running Postgres. Treat the leading digit as real and
  the decimal as noise.

### The one number to remember

Fusion narrowed the same-vs-different overlap by 40% — and still could not tell two
motorcycles apart. **The human in the loop is not a compliance checkbox in this
system. It is load-bearing.**
