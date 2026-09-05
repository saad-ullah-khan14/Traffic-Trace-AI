-- =====================================================================
-- Traffic_Trace — shared database schema
-- FROZEN at Integration Checkpoint A (Phase 2), 17 Aug 2026.
-- Changes after this point require agreement from BOTH teammates.
--
-- Target: PostgreSQL 18, native Windows service, database `traffic_trace`.
--
-- NOT pgvector. Embeddings are stored as float4[] and ranked by cosine
-- similarity in numpy inside the API worker. SQL performs the space-time
-- gate only. Production/scale path would be `vector(512)` + an hnsw index;
-- at demo scale a brute-force numpy dot product over a few hundred gated
-- candidates is faster than maintaining an index.
--
-- Apply with:
--   psql -U postgres -h 127.0.0.1 -d traffic_trace -f contracts/schema.sql
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- AGREED CONSTANTS
--
--   EMBEDDING_DIM = 512   CLIP ViT-B/32
--   Single source of truth: pipeline/types.py:EMBEDDING_DIM
--   The CHECK constraints below enforce it at the database boundary, so a
--   wrong-sized vector fails loudly on INSERT instead of silently ranking
--   badly later.
--
--   Embeddings arrive ALREADY L2-NORMALIZED from pipeline.process_frame.
--   Teammate 1 owns normalization; the API must not re-normalize. This
--   makes cosine similarity a plain dot product.
--
--   Reachability: max speed 60 km/h, 30-second grace period.
-- ---------------------------------------------------------------------


-- ---------------------------------------------------------------------
-- cameras — fixed phone camera positions
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cameras (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        text        NOT NULL,
    lat         double precision NOT NULL,
    lng         double precision NOT NULL,
    heading     real,                                  -- compass degrees 0-360, nullable
    token       text        NOT NULL UNIQUE,           -- checked on POST /api/frames
    created_at  timestamptz NOT NULL DEFAULT now()
);


-- ---------------------------------------------------------------------
-- sightings — EVERY vehicle at EVERY camera, always.
-- This is the core of the product: fingerprint everything, so that a
-- violation can later be matched against vehicles nobody flagged at the time.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sightings (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    camera_id     uuid        NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    ts            timestamptz NOT NULL,                -- when the frame was captured, not when it was processed
    vehicle_type  text        NOT NULL,                -- expected: motorcycle | car | rickshaw | truck | bus | other
                                                       -- intentionally unconstrained: exact label set is Teammate 1's
                                                       -- model output and not yet confirmed. Add a CHECK once it is.
    bbox          jsonb       NOT NULL,                -- [x1, y1, x2, y2] in pixels
    veh_emb       real[]      NOT NULL,                -- CLIP embedding of the vehicle crop, L2-normalized
    rider_emb     real[],                              -- rider crop; NULL when there is no rider
    attrs         jsonb       NOT NULL DEFAULT '{}'::jsonb,  -- {"color": "red", "helmet": false, "rider_count": 2}
    confidence    real,                                -- detector confidence, 0.0-1.0
    crop_path     text,                                -- path under evidence/
    crop_hash     text,                                -- SHA-256 of the crop file, for court-admissible evidence
    created_at    timestamptz NOT NULL DEFAULT now(),

    -- coalesce is load-bearing: array_length('{}'::real[], 1) is NULL, and a
    -- CHECK that evaluates to NULL PASSES. Without it an EMPTY embedding is
    -- accepted, producing a sighting that can never match anything, silently.
    CONSTRAINT sightings_veh_emb_dim
        CHECK (coalesce(array_length(veh_emb, 1), 0) = 512),
    CONSTRAINT sightings_rider_emb_dim
        CHECK (rider_emb IS NULL OR coalesce(array_length(rider_emb, 1), 0) = 512)
);

-- The space-time gate: "sightings at these cameras within this time window".
-- This is THE hot query of the matching engine (Phase 11).
-- Added 30 Aug 2026. A sighting records what was detected about it, violations
-- included. Needed because a violating sighting no longer always opens an
-- incident: if the vehicle is already an open case at another camera, it is
-- attached to that case instead. If the officer then says "not the same", the
-- sighting has to be promoted to its own incident, and that decision needs to
-- know a rule was broken. Empty array = nothing wrong was seen.
ALTER TABLE sightings ADD COLUMN IF NOT EXISTS violations text[] NOT NULL DEFAULT '{}';
-- Phase 4 of FIND_ME_PLAN.md: the whole frame the sighting came from, not
-- just the crop, so an officer reviewing a Find Me result can see the full
-- scene. NULL is normal — most sightings never get their frame recorded
-- (retention policy prunes old ones; see the frame-recording worker).
ALTER TABLE sightings ADD COLUMN IF NOT EXISTS frame_path text;

CREATE INDEX IF NOT EXISTS idx_sightings_camera_ts ON sightings (camera_id, ts DESC);

-- Retention sweep and time-only scans.
CREATE INDEX IF NOT EXISTS idx_sightings_ts ON sightings (ts);


-- ---------------------------------------------------------------------
-- incidents — opened ONLY when a violation is detected.
-- A readable plate makes this an ordinary e-challan; an unreadable plate
-- is what puts the system into fingerprint-matching mode.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS incidents (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    sighting_id uuid        NOT NULL REFERENCES sightings(id) ON DELETE CASCADE,
    violation   text        NOT NULL,                  -- expected: no_helmet | triple_riding | wrong_way | ...
    plate_text  text,                                  -- NULL = unreadable = fingerprint mode
    status      text        NOT NULL DEFAULT 'open',
    created_at  timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT incidents_status_valid CHECK (status IN ('open', 'confirmed', 'closed'))
);

-- Added 30 Aug 2026. When an officer confirms that a sighting belongs to an
-- existing case, and that sighting had opened a case of its own, the two are the
-- same offender and the second is folded into the first. It stays in the table
-- as a record; the feed simply stops showing it separately.
--
-- Merging is driven by the officer's confirm and nothing else. Doing it
-- automatically from a similarity score was tried and does not work: measured on
-- real footage, the SAME rider across two cameras scored 0.52-0.55 while six
-- DIFFERENT riders scored 0.69-0.75. The scores overlap the wrong way round, so
-- no threshold separates them.
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS merged_into uuid
    REFERENCES incidents(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_incidents_status_created ON incidents (status, created_at DESC);


-- ---------------------------------------------------------------------
-- matches — candidate sightings proposed for an incident, and the
-- officer's decision. Human-in-the-loop by design: the system proposes,
-- a person confirms. Never auto-confirmed.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS matches (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id uuid        NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    sighting_id uuid        NOT NULL REFERENCES sightings(id) ON DELETE CASCADE,
    score       real        NOT NULL,                  -- fused score from pipeline.score_candidates, 0.0-1.0
    breakdown   jsonb       NOT NULL DEFAULT '{}'::jsonb,  -- per-signal contributions, rendered as bars in the review UI
    decision    text,                                  -- NULL = undecided
    decided_at  timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT matches_decision_valid CHECK (decision IS NULL OR decision IN ('confirm', 'reject')),
    CONSTRAINT matches_unique_pair    UNIQUE (incident_id, sighting_id)
);

-- Review UI: top-K candidates for one incident, best first.
CREATE INDEX IF NOT EXISTS idx_matches_incident_score ON matches (incident_id, score DESC);


-- ---------------------------------------------------------------------
-- journeys — confirmed matches chained into a route.
-- One journey per incident; sighting_ids is ordered by time.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS journeys (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id uuid        NOT NULL UNIQUE REFERENCES incidents(id) ON DELETE CASCADE,
    sighting_ids uuid[]     NOT NULL DEFAULT '{}',     -- chronological order
    updated_at  timestamptz NOT NULL DEFAULT now()
);


COMMIT;

-- ---------------------------------------------------------------------
-- RETENTION (Phase 16)
-- Privacy commitment in the pitch: sightings not linked to any incident or
-- match are deleted after 48 hours. Implemented as a periodic job, not a
-- trigger, so it can be paused during a demo.
--
--   DELETE FROM sightings s
--   WHERE s.ts < now() - interval '48 hours'
--     AND NOT EXISTS (SELECT 1 FROM incidents i WHERE i.sighting_id = s.id)
--     AND NOT EXISTS (SELECT 1 FROM matches   m WHERE m.sighting_id = s.id);
-- ---------------------------------------------------------------------
-- ---------------------------------------------------------------------
-- search_audit — Phase 6 of FIND_ME_PLAN.md.
--
-- Find Me searches for people, which carries a responsibility: "who
-- searched for what, and when" must be answerable from the database
-- without reading a log file. Every search writes exactly one row here,
-- whether it found anything or not.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS search_audit (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    searched_at     timestamptz NOT NULL DEFAULT now(),
    mode            text        NOT NULL,           -- "vehicle" | "person"
    query_image_hash text       NOT NULL,            -- SHA-256, like crop_hash
    from_ts         timestamptz,
    to_ts           timestamptz,
    camera_ids      uuid[],
    vehicle_type    text,
    result_count    int         NOT NULL,
    confirmed_count int         NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_search_audit_searched_at ON search_audit (searched_at DESC);
-- ---------------------------------------------------------------------
-- search_confirmations — persists officer decisions made on Find Me
-- results, so they survive a page refresh and can feed Phase 5's
-- benchmark (real officer-labelled pairs, the same discipline
-- bench_matcher.py uses for incident matches).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS search_confirmations (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    search_id   uuid NOT NULL REFERENCES search_audit(id) ON DELETE CASCADE,
    sighting_id uuid NOT NULL REFERENCES sightings(id) ON DELETE CASCADE,
    decision    text NOT NULL,  -- 'confirm' | 'reject'
    decided_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_search_confirmations_search
    ON search_confirmations (search_id);
