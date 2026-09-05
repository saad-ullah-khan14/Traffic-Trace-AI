-- Migration 001 — close the empty-embedding hole in the dimension CHECKs.
--
-- Found by the Phase 6 audit. `array_length('{}'::real[], 1)` returns NULL, and
-- a CHECK constraint that evaluates to NULL is treated as PASSED. So an empty
-- embedding was accepted despite the constraint, producing a sighting that can
-- never match anything and gives no error to say why.
--
-- Safe to re-run.
--
--   psql -U postgres -h 127.0.0.1 -d traffic_trace -f contracts/migrations/001_fix_empty_embedding_check.sql

BEGIN;

ALTER TABLE sightings DROP CONSTRAINT IF EXISTS sightings_veh_emb_dim;
ALTER TABLE sightings DROP CONSTRAINT IF EXISTS sightings_rider_emb_dim;

ALTER TABLE sightings
    ADD CONSTRAINT sightings_veh_emb_dim
    CHECK (coalesce(array_length(veh_emb, 1), 0) = 512);

ALTER TABLE sightings
    ADD CONSTRAINT sightings_rider_emb_dim
    CHECK (rider_emb IS NULL OR coalesce(array_length(rider_emb, 1), 0) = 512);

COMMIT;
