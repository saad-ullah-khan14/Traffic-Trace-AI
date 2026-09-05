# Labelled test set — Traffic_Trace fingerprint

Real street footage. Real officer decisions. This is the only measurement that
counts, and it is the reason this folder exists: **nothing about the fingerprint
model should be changed on the strength of a synthetic test.** Identical images
posted to two cameras score 0.92; real crops of the same bike from two cameras
score 0.52–0.55. Only the second number is real, and it has cost this project
three wrong decisions already.

Read `teammate_starter/FINGERPRINT_UPGRADE.md` for why the current model fails.
This folder is Phase A of that brief, already built for you.

## Run it

```
python benchmark.py
```

Needs `numpy`, `pillow`, `torch`, and `open_clip_torch` for the baseline. The
same venv you use for `pipeline/` already has them.

It prints the three numbers that decide everything:

| | |
|---|---|
| **margin** | worst same-vehicle pair minus best different-vehicle pair, on cross-camera pairs. Positive = one threshold separates them. Negative = no threshold can. |
| **rank-1** | of the incidents with a confirmed match, how many put that match first. This is what the officer experiences. |
| **ms/crop** | speed on this CPU. The live machine runs at ~1.2 frames/s and the queue is a latency budget, not a buffer. |

## Change one thing

`build_embedder()` in `benchmark.py`. Nothing else. It returns a function
`crop_path -> L2-normalized numpy vector`, and a DINOv2 example is in its
docstring.

Three rules for whatever you put in it:

1. **Return unit vectors.** The API verifies normalization and warns rather than
   re-normalizing, so a model that stops normalizing degrades scores silently.
2. **Report the dimension.** If it is not 512, the backend needs a schema change
   (`contracts/schema.sql` has a CHECK constraint). Say so — do not pad or
   truncate a vector to fit.
3. **Cache the weights on disk.** The demo machine has no internet. No network
   call at inference time, ever.

## What is in `labels.json`

**`pairs`** — two kinds, and they are not interchangeable:

- `cross_camera` — the real task. One incident's own sighting against a
  candidate at another camera, labelled by the officer on the review screen.
  `same_vehicle: true` means they pressed *Same vehicle*.
- `burst` — two frames of one pass at one camera, gap ≤ 5 s. Same vehicle by
  construction, so nobody labelled them. They are a **floor**, reported
  separately: a model that cannot separate these cannot separate anything.
  Never quote a margin that mixes them in.

**`incidents`** — each incident's origin crop and its full candidate list with
labels, so a new model can re-rank exactly the set the officer saw. This is what
rank-1 is computed from.

## The bar

A change is kept only when **margin improves and rank-1 does not drop**, at
acceptable speed. Report all three, before and after.

If nothing clears the bar, say so plainly. That is a real result, and the
product survives it — the officer decides, and nothing is auto-confirmed. A
threshold tuned to hide the problem is not a result.

## Two baselines, and they are not the same thing

```
shipped fused score       margin  -0.066   rank-1  1/2
this script's embedder    margin  +0.018   rank-1  2/2
```

The first is what the officer actually sees: CLIP vehicle + CLIP rider + colour
histogram, fused by `pipeline/matcher.py`. Its negative margin means the score
cannot be fixed by tuning `MIN_CANDIDATE_SCORE`; that has been tried.

The second is raw cosine on the saved evidence crop, which includes the rider.
**It beats the fused score on the same 12 pairs** — which is a lead, not a
conclusion: there are only 2 confirmed cross-camera pairs, and a margin built on
2 positives is fragile.

What it points at, worth checking before anything expensive:

- the colour histogram carries the largest effective weight (0.46) and the worst
  separation (−0.364);
- the union crop (bike + rider), which is already saved for evidence, may be a
  better input than the tight vehicle box the pipeline embeds today.

Both are cheap to test with this folder. Do that before downloading a new model.

## More data

Every officer confirm and reject adds a label. Re-running
`api/scripts/export_labelset.py` after another session regenerates this folder
with everything collected so far — more is strictly better, especially more
cross-camera pairs, which are scarce.

Ask before pressing **Reset demo** on the dashboard: it deletes the crops and
the labels together. One set has already been lost that way.
