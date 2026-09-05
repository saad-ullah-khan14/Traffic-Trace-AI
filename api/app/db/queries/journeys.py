"""SQL for the journeys table — one route per incident."""

from typing import Any, Optional, Sequence
from uuid import UUID

import psycopg


def save_journey(
    conn: psycopg.Connection,
    incident_id: UUID,
    sighting_ids: Sequence[UUID],
) -> dict[str, Any]:
    """Create or replace the journey for an incident.

    A journey grows as the officer confirms more matches, so this upserts on
    incident_id rather than inserting a second row.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO journeys (incident_id, sighting_ids)
            VALUES (%s, %s::uuid[])
            ON CONFLICT (incident_id) DO UPDATE
                SET sighting_ids = EXCLUDED.sighting_ids,
                    updated_at = now()
            RETURNING id, incident_id, sighting_ids, updated_at
            """,
            (incident_id, list(sighting_ids)),
        )
        return cur.fetchone()


def get_journey(conn: psycopg.Connection, incident_id: UUID) -> Optional[dict[str, Any]]:
    """The journey with each hop's camera and timestamp, in chronological order.

    sighting_ids is an ordered array, so the join uses WITH ORDINALITY to
    preserve that order — array order is not row order in SQL.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT j.id, j.incident_id, j.updated_at,
                   coalesce(
                       json_agg(
                           json_build_object(
                               'sighting_id', s.id,
                               'ts',          s.ts,
                               'crop_path',   s.crop_path,
                               'camera_id',   c.id,
                               'camera_name', c.name,
                               'lat',         c.lat,
                               'lng',         c.lng
                           ) ORDER BY ord
                       ) FILTER (WHERE s.id IS NOT NULL),
                       '[]'::json
                   ) AS hops
            FROM journeys j
            LEFT JOIN unnest(j.sighting_ids) WITH ORDINALITY AS u(sighting_id, ord) ON true
            LEFT JOIN sightings s ON s.id = u.sighting_id
            LEFT JOIN cameras   c ON c.id = s.camera_id
            WHERE j.incident_id = %s
            GROUP BY j.id, j.incident_id, j.updated_at
            """,
            (incident_id,),
        )
        return cur.fetchone()
