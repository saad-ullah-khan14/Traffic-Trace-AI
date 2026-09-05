"""SQL for the incidents table.

An incident exists only where a violation was detected. Sightings are recorded
for every vehicle; incidents are the rare exception.
"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

import psycopg

from app.core.constants import MATCH_WINDOW_SECONDS


def insert_incident(
    conn: psycopg.Connection,
    sighting_id: UUID,
    violation: str,
    plate_text: Optional[str] = None,
) -> dict[str, Any]:
    """Open an incident. plate_text = None means unreadable, i.e. fingerprint mode."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO incidents (sighting_id, violation, plate_text)
            VALUES (%s, %s, %s)
            RETURNING id, sighting_id, violation, plate_text, status, created_at
            """,
            (sighting_id, violation, plate_text),
        )
        return cur.fetchone()


def merge_into(
    conn: psycopg.Connection, incident_id: UUID, into: UUID
) -> Optional[dict[str, Any]]:
    """Fold one case into another. Returns the merged row, or None if it is a no-op."""
    if incident_id == into:
        return None
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE incidents SET merged_into = %s
            WHERE id = %s AND merged_into IS NULL AND id <> %s
            RETURNING id, merged_into
            """,
            (into, incident_id, into),
        )
        return cur.fetchone()


def get_incident_for_sighting(
    conn: psycopg.Connection, sighting_id: UUID
) -> Optional[dict[str, Any]]:
    """The incident this sighting opened, if it opened one."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, violation, status FROM incidents WHERE sighting_id = %s",
            (sighting_id,),
        )
        return cur.fetchone()


def find_open_at_camera(
    conn: psycopg.Connection,
    camera_id: UUID,
    violation: str,
    since: datetime,
) -> Optional[dict[str, Any]]:
    """An incident already open for this violation at this camera since `since`.

    Used to stop one vehicle's single pass becoming several incidents. At 1 fps a
    bike is in shot for a handful of frames and the helmet model flags more than
    one of them, so the officer's queue filled with duplicate cards of the same
    rider.

    Matching on camera + violation + time rather than on appearance is
    deliberate. Measured across four frames of one bike at one camera:

        CLIP similarity   0.865 - 0.932
        colour overlap    0.32  - 0.78   (and the colour name flipped gray/blue)

    Both sit inside the range two *different* bikes produce, so no visual
    threshold can separate "same vehicle" from "another vehicle" here. Time can:
    one camera watches one spot, and one violation event happens there at a time.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT i.id, i.violation, i.plate_text, i.status, s.ts
            FROM incidents i
            JOIN sightings s ON s.id = i.sighting_id
            WHERE s.camera_id = %s
              AND i.violation = %s
              AND s.ts >= %s
            ORDER BY s.ts DESC
            LIMIT 1
            """,
            (camera_id, violation, since),
        )
        return cur.fetchone()


def get_incident(conn: psycopg.Connection, incident_id: UUID) -> Optional[dict[str, Any]]:
    """Incident joined to its originating sighting and camera, for the review UI."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT i.id, i.violation, i.plate_text, i.status, i.created_at,
                   s.id AS sighting_id, s.ts, s.vehicle_type, s.bbox, s.attrs,
                   s.veh_emb, s.rider_emb, s.crop_path, s.crop_hash, s.confidence,
                   c.id AS camera_id, c.name AS camera_name, c.lat, c.lng, c.heading
            FROM incidents i
            JOIN sightings s ON s.id = i.sighting_id
            JOIN cameras   c ON c.id = s.camera_id
            WHERE i.id = %s
            """,
            (incident_id,),
        )
        return cur.fetchone()


def list_incidents(
    conn: psycopg.Connection,
    status: Optional[str] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Feed listing, newest first, with a candidate count per incident.

    Cases an officer has folded into another are left out: one offender is one
    card, once a human has said so.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT i.id, i.violation, i.plate_text, i.status, i.created_at,
                   s.id AS sighting_id, s.ts, s.vehicle_type, s.crop_path,
                   c.id AS camera_id, c.name AS camera_name,
                   (SELECT count(*) FROM matches m WHERE m.incident_id = i.id) AS match_count
            FROM incidents i
            JOIN sightings s ON s.id = i.sighting_id
            JOIN cameras   c ON c.id = s.camera_id
            WHERE (%s::text IS NULL OR i.status = %s)
              AND i.merged_into IS NULL
            ORDER BY i.created_at DESC
            LIMIT %s
            """,
            (status, status, limit),
        )
        return cur.fetchall()


def set_incident_status(
    conn: psycopg.Connection,
    incident_id: UUID,
    status: str,
) -> Optional[dict[str, Any]]:
    """status must be one of open | confirmed | closed — enforced by a CHECK constraint."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE incidents SET status = %s WHERE id = %s
            RETURNING id, status
            """,
            (status, incident_id),
        )
        return cur.fetchone()


def get_open_for_watchlist(
    conn: psycopg.Connection,
    limit: int = 20,
    window_seconds: float = MATCH_WINDOW_SECONDS,
) -> list[dict[str, Any]]:
    """Open incidents with their originating sighting's fingerprint.

    Used to ask "is this vehicle one we are already looking for?" of every new
    sighting. Deliberately capped: watchlist checking runs on every vehicle at
    every camera, so an unbounded list would make ingest slower as the demo goes
    on — exactly when it must not.

    **Only plate-less incidents are watched.** Where the plate was read, the
    existing ANPR system already has everything it needs and is welcome to it;
    re-detecting that vehicle by fingerprint would burn ~10 ms on every passing
    vehicle to tell an officer something the plate already said.

    **Also bounded in time**, by the same window the space-time gate uses. Without
    it a stale incident alerts on everything: the required speed is distance over
    gap, so an hours-old incident needs a walking pace to be "reachable" and
    scores a near-perfect 1.0 on the heaviest-weighted signal. Measured on a
    replay against week-old incidents: unrelated vehicles alerted at 0.68-0.74,
    well over the 0.6 threshold. Beyond this window a match is a coincidence, not
    a reappearance — which is exactly what MATCH_WINDOW_SECONDS already says.
    """
    with conn.cursor(binary=True) as cur:
        cur.execute(
            """
            SELECT i.id AS incident_id, i.violation,
                   s.id AS sighting_id, s.camera_id, s.ts, s.vehicle_type,
                   s.veh_emb, s.rider_emb, s.attrs, s.crop_path,
                   c.lat, c.lng, c.name AS camera_name
            FROM incidents i
            JOIN sightings s ON s.id = i.sighting_id
            JOIN cameras   c ON c.id = s.camera_id
            WHERE i.status = 'open'
              AND i.plate_text IS NULL
              AND s.ts >= now() - make_interval(secs => %s)
            ORDER BY i.created_at DESC
            LIMIT %s
            """,
            (window_seconds, limit),
        )
        return cur.fetchall()
