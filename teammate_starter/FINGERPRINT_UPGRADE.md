# Fingerprint upgrade — brief for Teammate 1

**Written 31 Aug 2026, after two runs on real street footage.**
Owner: whoever owns `pipeline/`. Everything in this brief is inside that folder,
except the benchmark script, which lives in `api/scripts/`.

Read `HANDOFF.md` §4 first if you have not. This brief assumes it.

---

## 1. What is actually broken

The product works end to end. A violation is detected, an incident opens, the
officer is shown a short list, and their confirm builds the journey. That whole
chain was exercised on real footage on 31 Aug and it held.

**The candidate list is the broken part.** The officer is shown bikes that are
not remotely the same vehicle, and the true match does not rank first.

This is not a threshold problem and not a weights problem. It was measured:

### Measurement 1 — 18 labelled cross-camera pairs

One incident at Camera 1, three candidate passes at Camera 2, every frame of
each pass paired, labelled by the officer on the review screen (6 true pairs,
12 false):

| signal | true pairs | false pairs | margin |
|---|---|---|---|
| vehicle (CLIP cosine) | 0.851 – 0.923 | 0.722 – 0.926 | **−0.075** |
| rider (CLIP cosine) | 0.777 – 0.928 | 0.760 – 0.892 | **−0.115** |
| colour histogram | 0.506 – 0.781 | 0.642 – 0.870 | **−0.364** |

`margin = worst true pair − best false pair`. Every margin is negative: **no
single signal ranks all true pairs above all false pairs.** Colour is not merely
weak, it is inverted on this footage — the different bikes matched *better* on
colour, because the whole scene is grey: grey road, grey light, both riders in
dark clothes.

### Measurement 2 — the fused score puts the truth in the middle

```
0.856  different bike   rider 0.818  vehicle 0.864  colour 0.870
0.754  THE SAME BIKE    rider 0.862  vehicle 0.851  colour 0.636   <- officer confirmed
0.719  different bike   rider 0.805  vehicle 0.826  colour 0.605
```

The true match sits **between** two false ones. There is no value of
`MIN_CANDIDATE_SCORE` that keeps the truth and drops the rest. Raising it past
0.754 throws away the real vehicle.

### Measurement 3 — the clearest single failure

Second run, incident at 02:30:17: a lone male rider in a dark shirt. One of the
candidates offered was a motorcycle carrying **a child in front and a pillion
passenger behind**. Its `rider` similarity was **0.87**.

### Why

CLIP was trained to match an image to a *text description*. It learned what "a
person riding a motorcycle" looks like. Two different people on two different
motorcycles both encode as "person on motorcycle", so they land 0.85+ apart from
nothing. **CLIP encodes category, not identity.** This is not a bug in how it was
wired — it is the wrong tool for a re-identification task.

`pipeline/fingerprint.py` already says as much in its own docstring, and the
colour histogram was added to compensate. On this footage that compensation
fails too.

---

## 2. The bar to clear

Define success **before** changing anything, and measure every attempt the same
way. A change is worth keeping only if, on the labelled set:

1. **Rank-1**: the officer-confirmed match ranks **first** among candidates.
2. **Margin > 0**: worst true pair scores above best false pair.
3. **Latency**: the fingerprint step stays inside the frame budget. The machine
   currently manages ~1.2 frames/s and `QUEUE_MAXSIZE = 8` is a latency budget,
   not a buffer — see `HANDOFF.md` §4. A model that doubles fingerprint time
   pushes incidents past the point where they are visible in time.

Today's baseline on all three: **rank-1 fails, margin −0.075, latency OK.**

---

## Phase A — DONE. The benchmark is built and comes with the brief.

You are getting a folder, `labelset/`, about 800 KB. It runs on your machine with
**no database, no API and no project imports** — numpy, pillow, torch, and
whatever your model needs.

```
python benchmark.py
```

| | |
|---|---|
| `crops/` | 26 real crops, the ones the officer actually looked at |
| `labels.json` | 12 cross-camera pairs (2 same, 10 different) + 41 free burst pairs |
| `benchmark.py` | margin, rank-1, ms/crop. **Edit `build_embedder()` and nothing else** |
| `README.md` | the rules for what counts as an improvement |

Labels are the officer's own confirm/reject decisions on real footage, exported
by `api/scripts/export_labelset.py`. Re-running that script after another
labelling session regenerates the folder with more pairs — ask for a fresh one,
cross-camera pairs are the scarce part.

### Two baselines print every run. They are not the same thing.

```
shipped fused score       margin  -0.066   rank-1  1/2
this script's embedder    margin  +0.018   rank-1  2/2
```

The first is what the officer sees: CLIP vehicle + CLIP rider + colour histogram,
fused by `matcher.py`. The second is raw cosine on the **saved evidence crop**,
which includes the rider.

**The second beats the first on the same twelve pairs.** Two cheap things to test
with this folder before downloading any new model:

- the colour histogram carries the largest effective weight (0.46, see Phase E)
  and the worst separation (−0.364). Try dropping it.
- the union crop (bike + rider) is already saved for evidence but never embedded;
  the pipeline embeds a tighter vehicle box. Try embedding the union.

Treat this as a lead, not a result: **there are only 2 confirmed cross-camera
pairs.** A margin built on 2 positives is fragile, and this is exactly the kind
of number that has misled this project before. More labels first.

---

## Phase B — Average the embedding over a pass. No new model.

This is free, uses the model already loaded, and is standard practice in
re-identification (temporal pooling): a single frame is noisy, the mean of a
track's frames is much less so.

Two or three frames per pass are already stored. Instead of comparing one frame
to one frame, compare the **L2-normalized mean** of the origin pass's embeddings
to the L2-normalized mean of each candidate pass's embeddings.

The API already groups frames into passes — `collapse_bursts` in
`api/app/services/matching.py`, same camera, 5 s window. It currently keeps the
single clearest frame; the grouping it computes is what you want.

Run Phase A before and after. Keep it only if the margin improves.

**Cost:** an afternoon. **Expected:** a real but modest gain; noise drops, the
category-vs-identity problem does not.

---

## Phase C — Replace the encoder. This is the main event.

Test in this order, cheapest first, and take the first one that clears the bar in
Phase A. Do not stack them.

### C1. DINOv2 — try this first

`timm 1.0.28` is already installed, so this needs no new dependency:
`vit_small_patch14_dinov2` (~85 MB) or `vit_base_patch14_reg4_dinov2` (~350 MB).

DINOv2 is self-supervised and is specifically strong at **instance-level
retrieval** — "this exact object again" rather than "another object of this
kind". That is precisely the gap CLIP leaves.

### C2. Person re-ID on the rider crop

Models trained on Market-1501 / DukeMTMC (OSNet, ResNet-50 re-ID) are trained on
exactly our question: *is this the same person, seen from a different camera?*
Training pulls same-person pairs together and pushes different-person pairs
apart — the objective CLIP never had.

This is likely the strongest signal available for this product, because on
commuter motorcycles **the rider is the distinctive part** — the bikes really are
near-identical. The officer recognises the person. So should the model.

The 02:30 failure above (child + pillion scoring 0.87) is the kind of case a
person re-ID model is built to get right.

### C3. Vehicle re-ID

Weights trained on VeRi-776 / VehicleID exist, but those datasets are **cars**.
Transfer to motorcycles is unproven. Try it only if C1 and C2 both fail.

### Rules for this phase

- **Download once, cache locally.** The demo machine runs offline; weights must
  live on disk. No network call at inference time, ever.
- **Measure latency, not just accuracy.** Report ms per crop on this CPU.
- Keep the output contract identical: L2-normalized vector, and
  `EMBEDDING_DIM` in `pipeline/fingerprint.py` must match `contracts/schema.sql`
  (`float4[]`, currently 512, with a CHECK constraint) and
  `api/app/core/constants.py`. **If the new model's dimension differs, that is a
  schema migration and a contract change — flag it before writing code.**
- The API verifies normalization and warns rather than re-normalizing
  (`assert_normalized`). Keep returning unit vectors.

---

## Phase D — Signals that are not vision

Vision is being asked to do all the work. These are cheap and independent.

### D1. `passenger_count` — computed, stored, and never used

`fingerprint()` takes it, `orchestrator.py` fills it from `detect()`'s
`rider_count`, it is stored in `sightings.attrs` — and `score_candidates` never
reads it. One rider versus three people is a decisive mismatch, and it is free.

**But fix it first: it is currently wrong.** In the 02:30 run, the bike carrying
a child and a pillion passenger was recorded as `passenger_count = 1`. Small and
partly occluded people are being missed. Measure the person count against the
crops before using it for anything, and prefer it as a **hard filter** (counts
differ by more than one → not a candidate) over another weighted number.

### D2. `helmet_color` — stored, unused

Same situation. Lower value than the passenger count, but free.

### D3. Direction of travel

Not computed today. Within one burst the bounding box moves and grows; that gives
approach-vs-recede, and possibly left-vs-right. A vehicle heading the other way is
not the same journey. This is new work — only worth it if C and D1 leave a gap.

---

## Phase E — Re-tune the weights. Only after A–D.

Current weights in `pipeline/matcher.py` are hand-set:

```
WEIGHT_VEHICLE = 0.20   WEIGHT_RIDER = 0.15
WEIGHT_ATTRIBUTES = 0.30   WEIGHT_SPACE_TIME = 0.35
```

Two things about them:

- `WEIGHT_SPACE_TIME = 0.35` is **dead weight in practice**. The API deliberately
  does not send `distance_m` / `time_gap_seconds` — space-time was measured as
  inverted on real footage and it is already enforced as a gate before scoring.
  `score_candidates` redistributes the missing weight, which is correct; just know
  that the effective weights are vehicle 0.31, rider 0.23, attributes 0.46.
- `WEIGHT_ATTRIBUTES = 0.30` is therefore the **largest** effective weight, and
  it is on the colour histogram — the signal measured at margin **−0.364**, the
  worst of the three. On this footage the heaviest weight is on the most
  misleading signal.

Do not hand-adjust these. Once a signal from Phase C actually separates, fit the
weights on the Phase A benchmark and report the before/after margin.

---

## Phase F — If nothing clears the bar

Say so plainly and do not disguise it with a number. The product design already
survives this outcome: the system narrows, the officer decides, and nothing is
auto-confirmed. In that case the work moves to the review screen — fewer, better
candidates and faster rejection — not to the model.

That is an acceptable answer. A tuned threshold that hides the problem is not.

---

## Hard rules, learned the expensive way

1. **Never measure on synthetic input.** Identical images posted to two cameras,
   random vectors, hand-picked stills. Three wrong decisions in one day came from
   this. Two motorcycles that are genuinely the same score 0.52–0.55 on real
   crops; the same image posted twice scores 0.92. Only the first number is real.
2. **Never tune a threshold to fix a bad candidate list.** If the ranking is
   wrong, the threshold is not the thing that is wrong.
3. **A count is not a check, and neither is a hash.** Render the thing and look
   at it. Two tile providers passed every automated check while serving "API KEY
   REQUIRED" across every image.
4. **When a test fails, check the test first.** Twice the code was right and the
   test's wait helper returned before the worker had finished.
5. **`pipeline/` must never import from `api/`.** Pure functions, no DB, no HTTP.
   `api/app/services/pipeline_client.py` is the only file that crosses over.
6. **Do not change the crop contract casually.** Evidence crops include the rider
   on purpose (`save_crop(..., also=rider_bboxes)`, 1.49–1.81× taller) because
   the rider is what an officer recognises — and, per Phase C2, probably what the
   model should recognise too.

---

## Order of work, and what each is worth

| Phase | Effort | Expected gain | Blocks |
|---|---|---|---|
| **A** benchmark from real labels | half a day | none directly — makes everything else measurable | everything |
| **B** average over a pass | half a day | small, free, keep if positive | — |
| **C1** DINOv2 | one day | **largest single expected gain** | needs A |
| **C2** person re-ID on rider | one to two days | likely largest of all for this product | needs A |
| **C3** vehicle re-ID | one day | uncertain, cars ≠ motorcycles | needs A |
| **D1** fix + use passenger count | half a day | decisive on the worst failures | — |
| **D2** helmet colour | an hour | small | — |
| **D3** direction of travel | one to two days | unknown | needs C, D1 |
| **E** re-tune weights | half a day | only after a signal separates | needs A + C |

**Start at A. Then C1 and D1 in parallel if there are two of you.**

---

## What already exists, so it is not rebuilt

| | |
|---|---|
| `api/scripts/bench_embeddings.py` | margin calculation, needs a DB-backed label source |
| `matches.decision` | every officer confirm/reject is already a stored label |
| `evidence/` | every crop the officer looked at, on disk |
| `collapse_bursts` in `api/app/services/matching.py` | frames already grouped into passes, 5 s window |
| `pipeline/dedupe.py` | written, **never wired, and its 0.95 similarity threshold does not work** — same-pass cosine measured 0.850–0.943, different-bike 0.691–0.889, overlapping. Time separates these cleanly; similarity does not. Delete it or rewrite it on time |
| `pipeline/selftest.py` | keep it passing |
