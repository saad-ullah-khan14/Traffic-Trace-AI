# pipeline/ — Teammate 1 (AI)

Pure Python functions. **No database access, no HTTP, no FastAPI imports here.**
`api/` is the only code that touches Postgres and the network; it imports and calls these.

## Functions to provide

| Function | Purpose |
|---|---|
| `process_frame` | frame → detections, embeddings, attributes, violations |
| `read_plate` | plate crop → text, or None when unreadable |
| `score_candidates` | fuse vehicle / rider / attribute / space-time signals into a ranked list |
| `is_reachable` | can a vehicle seen at camera A reach camera B in this time gap? |
| `check_watchlist` | does a new sighting match an open incident? |
| `build_journey` | confirmed matches → an ordered route |
| `dedupe` | collapse repeated sightings of the same vehicle at one camera |

Signatures are frozen jointly in `pipeline/types.py` during **Phase 2**.

## Environment

**Python 3.12** — same as `api/`. Create with `py -3.12 -m venv`, not bare `python`.
The default `python` on this machine is 3.14 and has no wheels for torch/onnxruntime.

## ⚠️ Changes from the original roadmap

- **No pgvector.** Embeddings are stored as `float4[]` and ranked by cosine in numpy
  inside the API worker. This does not change any signature here — `score_candidates`
  still receives embeddings — but the database no longer performs similarity search.
- **No Docker.** Postgres runs as a native Windows service.

Open question to settle before Phase 11: does `score_candidates` expect *all*
space-time-gated candidates, or the top-K already ranked by visual similarity?

Model weights go in `pipeline/weights/` and are gitignored — too large for the repo.
