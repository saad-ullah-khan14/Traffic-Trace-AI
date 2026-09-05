# contracts/ — shared, frozen jointly

**Filled in during Phase 2 (Integration Checkpoint A). Do not write these alone.**

| File | Contents |
|---|---|
| `schema.sql` | the five tables: cameras, sightings, incidents, matches, journeys |
| `endpoints.md` | REST + WebSocket surface the dashboard and camera page rely on |
| `../pipeline/types.py` | dataclasses passed between `pipeline/` and `api/` |

After Checkpoint A these change **only by joint agreement**.

## Already decided (see PROGRESS.md §4-5)

- `veh_emb` / `rider_emb` are **`float4[]`**, not `vector(DIM)` — no pgvector.
  Stored L2-normalized so cosine reduces to a dot product.
- Postgres **18**, native Windows service, database `traffic_trace`.

## Still blocking Phase 2

- **Embedding dimension** — 2048 (fast-reid) or 512 (CLIP), from Teammate 1's ReID spike.
  Set it in ONE shared constant; everything downstream inherits it.
- **The `is_reachable` rule** — the SQL space-time gate must match Teammate 1's Python
  implementation exactly, or Phase 11 hands the scorer candidates it never expected.
