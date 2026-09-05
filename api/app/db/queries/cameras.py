"""SQL for the cameras table."""

from typing import Any, Optional
from uuid import UUID

import psycopg


def insert_camera(
    conn: psycopg.Connection,
    name: str,
    lat: float,
    lng: float,
    heading: Optional[float],
    token: str,
) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO cameras (name, lat, lng, heading, token)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, name, lat, lng, heading, token, created_at
            """,
            (name, lat, lng, heading, token),
        )
        return cur.fetchone()


def get_camera(conn: psycopg.Connection, camera_id: UUID) -> Optional[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, name, lat, lng, heading, created_at FROM cameras WHERE id = %s",
            (camera_id,),
        )
        return cur.fetchone()


def get_camera_by_token(conn: psycopg.Connection, token: str) -> Optional[dict[str, Any]]:
    """Used to authenticate POST /api/frames (Phase 5)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, name, lat, lng, heading FROM cameras WHERE token = %s",
            (token,),
        )
        return cur.fetchone()


def update_camera_location(
    conn: psycopg.Connection,
    camera_id: UUID,
    lat: float,
    lng: float,
) -> Optional[dict[str, Any]]:
    """Move a camera to a reported GPS fix, or a manually dragged pin.

    Position feeds the reachability gate, so this is not cosmetic: moving a
    camera changes which past sightings are considered reachable from it.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE cameras SET lat = %s, lng = %s WHERE id = %s
            RETURNING id, name, lat, lng, heading, created_at
            """,
            (lat, lng, camera_id),
        )
        return cur.fetchone()


def list_cameras(conn: psycopg.Connection) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, name, lat, lng, heading, created_at FROM cameras ORDER BY created_at"
        )
        return cur.fetchall()
