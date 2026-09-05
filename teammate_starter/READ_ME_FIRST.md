> **SUPERSEDED — kept only as a record.** This starter kit did its job: Teammate 1
> built against it and `process_frame` matched on the first try, with no field-name
> mismatches. The live contract is now `pipeline/types.py`, which he delivered in
> Phase 7. The `types.py` in this folder is an earlier, divergent draft — do not
> use it, and do not treat anything here as current.

# Read this first

This folder is your starting point for the AI side of Traffic_Trace.

**What to do:** put your code inside `pipeline/`, run `selftest.py`, and when
everything says PASS, send the whole `pipeline/` folder back.

You do **not** need the database, the API, or the dashboard to work on this.
Your code is pure Python functions — the backend imports them and does the rest.

---

## Setup

```powershell
# Python 3.12 exactly. Not 3.11, not 3.13/3.14 - the AI libraries have no
# working builds for those yet and installation fails with confusing errors.
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r pipeline\requirements.txt
```

---

## What you are building

Seven functions. `pipeline/__init__.py` must expose all seven so that
`from pipeline import process_frame` works.

| Function | What it does | Where it is used |
|---|---|---|
| `process_frame` | photo → list of vehicles, each with a 512-number fingerprint | every frame from every phone |
| `read_plate` | plate crop → text, or `None` | when a violation is found |
| `is_reachable` | could a vehicle get from A to B in this time? | filtering candidates |
| `score_candidates` | rank the 20 candidates we send you | the officer's review screen |
| `check_watchlist` | does this new vehicle match an open case? | reappearance alerts |
| `build_journey` | confirmed matches → a route | the map animation |
| `dedupe` | collapse repeat sightings of one vehicle at one camera | after processing |

`process_frame` is by far the most important. The other six are small.

---

## The three rules that actually matter

**1. Embeddings must be exactly 512 numbers.**
The database rejects anything else, loudly.

**2. Embeddings must be L2-normalized** — their length must be exactly 1.0:

```python
import numpy as np
emb = emb / np.linalg.norm(emb)   # do this before returning
```

This is the single most commonly missed step. If you skip it, **nothing errors**
— match scores are just quietly wrong and the demo looks broken for no visible
reason. `selftest.py` checks it.

**3. Never import anything from `api/`.**
Your code must never touch the database or the network. The backend calls you,
not the other way round. If you need a value, it gets passed in as an argument.

---

## Field names

`pipeline/types.py` has the proposed shapes. If yours differ, edit that file and
say so — the backend already accepts common alternatives (`box` for `bbox`,
`embedding` for `veh_emb`, and so on), so small differences are fine.

What is **not** fine is a difference nobody mentions. A name mismatch produces
no error at all — just empty results — and both sides spend a day assuming the
other one is broken.

---

## Before you send it back

Run it from **this** folder — the one that contains `pipeline/`, not from inside it:

```powershell
.\.venv\Scripts\python.exe -m pipeline.selftest
```

Every line must say PASS.

Then send:

- the `pipeline/` folder
- `pipeline/requirements.txt`, updated with whatever you installed
- the model weight files **separately** (WhatsApp/USB — they are too big for git)
- a one-line note: what exact strings your model outputs for `vehicle_type`
  (`"motorcycle"`? `"motorbike"`?) and for violations (`"no_helmet"`?)

Do **not** send `.venv/` — it is hundreds of MB and only works on your machine.

---

## One thing that changed since the roadmap

If you write `tools/replay.py`, the camera token goes in a **header**, not a
form field. The old `endpoints.md` said otherwise and was wrong:

```bash
curl -X POST http://<laptop-ip>:8000/api/frames \
  -H "X-Camera-Token: <the camera secret>" \
  -F "frame=@frame.jpg" \
  -F "ts=2026-08-22T14:03:11Z"
```

Sending the token as a form field gives **401 on every frame**.
