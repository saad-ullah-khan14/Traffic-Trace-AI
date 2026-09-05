"""SQL for the matches table — proposed candidates and the officer's decision."""

import json
from typing import Any, Optional, Sequence
from uuid import UUID

import psycopg


def save_matches(
    conn: psycopg.Connection,
    incident_id: UUID,
    scored: Sequence[tuple[UUID, float, dict[str, Any]]],
) -> int:
    """Store ranked candidates for an incident.

    `scored` is (sighting_id, score, breakdown) as returned by
    pipeline.score_candidates. Re-running matching for the same incident updates
    scores in place rather than duplicating rows — the UNIQUE (incident_id,
    sighting_id) constraint makes that an upsert. An officer's existing decision
    is never overwritten.
    """
    if not scored:
        return 0

    with conn.cursor() as cur:
        # Anything previously offered for this incident that is no longer a
        # candidate is dropped, so the review screen shows the current answer
        # rather than the union of every answer ever given. A row the officer
        # has already decided is never touched.
        cur.execute(
            """
            DELETE FROM matches
             WHERE incident_id = %s
               AND decision IS NULL
               AND NOT (sighting_id = ANY(%s))
            """,
            (incident_id, [sighting_id for sighting_id, _, _ in scored]),
        )

        cur.executemany(
            """
            INSERT INTO matches (incident_id, sighting_id, score, breakdown)
            VALUES (%s, %s, %s, %s::jsonb)
            ON CONFLICT (incident_id, sighting_id) DO UPDATE
                SET score = EXCLUDED.score,
                    breakdown = EXCLUDED.breakdown
                WHERE matches.decision IS NULL
            """,
            [
                (incident_id, sighting_id, score, json.dumps(breakdown or {}))
                for sighting_id, score, breakdown in scored
            ],
        )
        return cur.rowcount


def get_matches_for_incident(
    conn: psycopg.Connection,
    incident_id: UUID,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Candidates for the review UI, best first, each with its sighting and camera.

    No score cut. There used to be one — `score >= MIN_CANDIDATE_SCORE` — and it
    was measured on 1 Sep against the officer's own labels: **21 of 21 candidates
    scored above it**, so it excluded nothing, while its only demonstrated
    behaviour on earlier runs was to hide a true match without saying so.

    The reason is in the numbers: confirmed matches scored 0.853-0.951, rejected
    ones 0.730-0.930. They overlap, so no absolute threshold separates them. But
    the ORDER is right — the true match ranked first in every incident (3/3). The
    score is a ranking signal, not a verdict, so the cut belongs where ranking can
    be used: the review screen keeps the top few and puts the rest one click away.
    Everything is returned here, best first.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT m.id, m.score, m.breakdown, m.decision, m.decided_at,
                   s.id AS sighting_id, s.ts, s.vehicle_type, s.attrs,
                   s.crop_path, s.crop_hash, s.confidence,
                   c.id AS camera_id, c.name AS camera_name, c.lat, c.lng
            FROM matches m
            JOIN sightings s ON s.id = m.sighting_id
            JOIN cameras   c ON c.id = s.camera_id
            WHERE m.incident_id = %s
            ORDER BY m.score DESC
            LIMIT %s
            """,
            (incident_id, limit),
        )
        return cur.fetchall()


def decide_match(
    conn: psycopg.Connection,
    match_id: UUID,
    decision: str,
) -> Optional[dict[str, Any]]:
    """Record confirm or reject. Anything else is rejected by a CHECK constraint."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE matches
               SET decision = %s, decided_at = now()
             WHERE id = %s
            RETURNING id, incident_id, sighting_id, decision, decided_at
            """,
            (decision, match_id),
        )
        return cur.fetchone()


def get_confirmed_sightings(
    conn: psycopg.Connection,
    incident_id: UUID,
) -> list[dict[str, Any]]:
    """Confirmed matches in time order — the raw material for a journey."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT s.id AS sighting_id, s.ts, s.crop_path,
                   c.id AS camera_id, c.name AS camera_name, c.lat, c.lng,
                   m.score
            FROM matches m
            JOIN sightings s ON s.id = m.sighting_id
            JOIN cameras   c ON c.id = s.camera_id
            WHERE m.incident_id = %s AND m.decision = 'confirm'
            ORDER BY s.ts
            """,
            (incident_id,),
        )
        return cur.fetchall()
