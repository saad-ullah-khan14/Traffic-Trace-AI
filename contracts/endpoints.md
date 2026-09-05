# API contract

**Frozen at Integration Checkpoint A (Phase 2), 17 Aug 2026.** Changes require agreement from both teammates.

Base URL in development: `http://localhost:8000` — or `http://<laptop-ip>:8000` from phones on the hotspot.

Interactive docs: `/docs` · machine-readable spec: `/openapi.json`

---

## Agreed constants

| Constant | Value | Owner |
|---|---|---|
| `EMBEDDING_DIM` | **512** (CLIP ViT-B/32) | `pipeline/types.py` is the single source of truth |
| Normalization | embeddings arrive **already L2-normalized** | Teammate 1. The API must **not** re-normalize |
| Max speed | **60 km/h** | used identically by the SQL gate and `pipeline.is_reachable` |
| Grace period | **30 seconds** | as above |
| Candidate handoff | API sends **top-20, already visually ranked** | `pipeline.score_candidates` fuses the remaining signals |
| bbox format | `[x1, y1, x2, y2]` in pixels | |
| Confidence / score scale | `0.0`–`1.0` floats | |

---

## REST

### `GET /api/health`
Liveness plus a real Postgres round-trip. **Built.**

```json
{"status": "ok", "db": {"ok": true, "database": "traffic_trace", "version": "PostgreSQL 18.4"}}
```

### `POST /api/cameras` — Phase 4
Register a camera position. Returns a token the phone stores and sends with every frame.

```jsonc
// request
{"name": "Ferozepur Rd / Kalma Chowk", "lat": 31.5102, "lng": 74.3341, "heading": 135}
// response 201
{"id": "uuid", "name": "...", "lat": 31.5102, "lng": 74.3341, "heading": 135, "token": "opaque-string"}
```

### `POST /api/frames` — Phase 5 · **built**
The ingest endpoint. `multipart/form-data`, one JPEG per request.

> ⚠️ **Auth is a header, not a form field.** The camera is identified by
> `X-Camera-Token`; there is no `camera_id` or `token` field in the body. A
> client that sends them as form fields gets **401 on every frame**.
> (This block previously documented form-field auth and did not match the code —
> corrected 18 Aug 2026. `tools/replay.py` must send the header.)

**Header:** `X-Camera-Token: <the camera's secret>`

| Form field | Type | Notes |
|---|---|---|
| `frame` | file | JPEG |
| `ts` | ISO 8601 | **capture** time from the phone, not arrival time. Optional; defaults to arrival |

```bash
curl -X POST http://<laptop-ip>:8000/api/frames \
  -H "X-Camera-Token: YBYkUsIH0QwGmG1_mdyXI-QmoD6Lu1iU" \
  -F "frame=@frame.jpg" \
  -F "ts=2026-08-22T14:03:11Z"
```

Returns **202 Accepted immediately** after queueing — it does not wait for AI inference. A phone blocked on inference would stall its capture loop and drop frames.

```json
{"accepted": true, "queued": 1}
```

### `GET /api/incidents` — Phase 9
List for the incident feed, newest first. Query: `?status=open&limit=50`.

```jsonc
[{
  "id": "uuid", "violation": "no_helmet",
  "plate_text": null,                 // null = unreadable = fingerprint mode
  "status": "open", "created_at": "2026-08-22T14:03:11Z",
  "camera": {"id": "uuid", "name": "Kalma Chowk"},
  "crop_url": "/evidence/<sha256>.jpg",
  "match_count": 12
}]
```

### `GET /api/incidents/{id}` — Phase 11
> ⚠️ **Product boundary, added 30 Aug 2026.** `matches` is **empty by design**
> whenever `plate_text` is not null. A readable plate is handled by the existing
> ANPR system, so the space-time gate, ranking and the watchlist are all skipped
> for that incident. An empty `matches` on a plate-read incident is correct
> behaviour, not a matching failure — the review UI says "handled by ANPR"
> instead of showing an empty candidate list.

Everything the review UI needs in one call: the violation evidence, and ranked candidates with their score breakdown.

```jsonc
{
  "id": "uuid", "violation": "no_helmet", "plate_text": null, "status": "open",
  "sighting": {
    "id": "uuid", "ts": "...", "vehicle_type": "motorcycle",
    "camera": {"id": "uuid", "name": "Kalma Chowk", "lat": 31.51, "lng": 74.33},
    "crop_url": "/evidence/<sha256>.jpg",
    "attrs": {"color": "red", "helmet": false, "rider_count": 2}
  },
  "matches": [{
    "id": "uuid", "score": 0.87,
    "breakdown": {"vehicle": 0.91, "rider": 0.78, "attributes": 0.83, "space_time": 0.95},
    "decision": null,
    "sighting": { /* same shape as above */ }
  }]
}
```

`breakdown` keys drive the score bars in the review UI. Whatever `score_candidates` puts there is what gets rendered.

### `POST /api/matches/{id}/decision` — Phase 10
The officer's confirm/reject. Confirming triggers `build_journey` and emits `journey_update`.

```jsonc
// request
{"decision": "confirm"}   // or "reject"
// response
{"id": "uuid", "decision": "confirm", "decided_at": "..."}
```

### `GET /api/journeys/{incident_id}` — Phase 13
The route built from confirmed matches, in chronological order. **404 until at
least one match is confirmed** — a single stop is a violation, not a journey.

> ⚠️ **Corrected 29 Aug 2026.** This block used to describe a `hops` / `sightings`
> shape with a precomputed OSRM `path`. That was never built: `pipeline.build_journey`
> returns a flat **`stops`** list where each stop carries its own hop back to the
> previous one, and the dashboard reads exactly that. There is no OSRM dependency —
> `JourneyMap.tsx` draws a straight polyline through the stops. Anyone testing
> against the old shape sees an empty journey and concludes, wrongly, that the
> feature is broken.

```jsonc
{
  "incident_id": "uuid",
  "total_span_seconds": 450.0,
  "total_distance_km": 3.469,          // exactly equal to the sum of hop_distance_km
  "stops": [{                          // oldest first; stop 1 is always the violation
    "sighting_id": "uuid",
    "camera_id": "uuid",
    "camera_name": "Camera 1 — Shahrah-e-Faisal",
    "ts": "2026-08-29T17:00:00+00:00",
    "lat": 25.011, "lon": 67.0403,     // NOTE: `lon`, not `lng` — his naming
    "hop_confidence": 1.0,             // 1.0 on stop 1: the violation is certain
    "hop_distance_km": 0.0,            // 0 on stop 1: no previous stop
    "hop_seconds": 0.0,
    "crop_url": "/evidence/<sha256>.jpg"
  }]
}
```

### `GET /evidence/{filename}` — Phase 4
Static serving of crop images. Filenames are the SHA-256 of the file contents.

---

## WebSocket

### `WS /ws/live` — Phase 8
One connection, all events. The client auto-reconnects with backoff.

Every message: `{"type": "...", "data": {...}}`

| `type` | Emitted when | Consumed by |
|---|---|---|
| `sighting` | a sighting is stored | live map — camera activity pulse |
| `incident` | a violation opens an incident | incident feed |
| `match_suggestion` | candidates ranked, or `check_watchlist` fires | review UI, alert toast |
| `journey_update` | a match is confirmed and the journey grows | journey map animation |

```jsonc
{"type": "incident", "data": {
  "id": "uuid", "violation": "no_helmet", "plate_text": null,
  "camera": {"id": "uuid", "name": "Kalma Chowk"},
  "crop_url": "/evidence/<sha256>.jpg", "created_at": "..."
}}
```

---

## Errors

Standard FastAPI shape, `{"detail": "..."}`.

| Code | Meaning |
|---|---|
| 400 | malformed request |
| 401 | bad or missing camera token |
| 404 | unknown id |
| 413 | frame too large |
| 422 | validation failed (FastAPI generates this) |

---

## Functions the API calls from `pipeline/`

Owned by Teammate 1; signatures in `pipeline/types.py`.

| Function | Called from | Phase |
|---|---|---|
| `process_frame` | `services/ingest.py` | 5 (stub) → 7 (real) |
| `read_plate` | `services/ingest.py` | 7 |
| `is_reachable` | mirrored by the SQL gate in `db/queries/sightings.py` | 11 |
| `score_candidates` | `services/matching.py` — receives **top-20 pre-ranked** | 11 |
| `check_watchlist` | `workers/frame_worker.py` | 14 |
| `build_journey` | `services/journeys.py` | 13 |
| `dedupe` | `services/ingest.py` | 7 |

**Dependency rule:** `api/` imports `pipeline/`. `pipeline/` must never import from `api/`, and must never touch the database or the network.

---

## Still open

- [ ] **Exact field names on Teammate 1's dataclasses** (`Detection`, `Fingerprint`, `Sighting`, `Violation`, `FrameResult`, `MatchCandidate`, `Journey`). Field-name mismatches fail *silently* — empty results, no error. Highest-risk open item.
- [ ] `vehicle_type` label set — `sightings.vehicle_type` is deliberately left unconstrained until confirmed; add a `CHECK` once known.
- [ ] `violation` label set — same.
- [ ] `attrs` keys — the review UI renders these; `{"color", "helmet", "rider_count"}` assumed.
