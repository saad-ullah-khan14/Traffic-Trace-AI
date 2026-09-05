"""SQL for the Find Me search audit trail. Kept out of the route
(search.py) on purpose — FIND_ME_PLAN.md's layering rule says the route
contains no SQL, matching how every other resource in this project
(incidents, matches, journeys) is structured.
"""
from typing import Any, Optional
from uuid import UUID


def insert_search_audit(
    conn,
    mode: str,
    query_image_hash: str,
    from_ts,
    to_ts,
    camera_ids: Optional[list],
    vehicle_type: Optional[str],
    result_count: int,
) -> UUID:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO search_audit (
                mode, query_image_hash, from_ts, to_ts,
                camera_ids, vehicle_type, result_count
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (mode, query_image_hash, from_ts, to_ts, camera_ids, vehicle_type, result_count),
        )
        return cur.fetchone()["id"]


def get_search_audit(conn, search_id: UUID) -> Optional[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM search_audit WHERE id = %s", (search_id,))
        return cur.fetchone()


def insert_search_confirmation(
    conn, search_id: UUID, sighting_id: UUID, decision: str
) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO search_confirmations (search_id, sighting_id, decision)
            VALUES (%s, %s, %s)
            RETURNING id, decided_at
            """,
            (search_id, sighting_id, decision),
        )
        row = cur.fetchone()
        if decision == "confirm":
            cur.execute(
                "UPDATE search_audit SET confirmed_count = confirmed_count + 1 WHERE id = %s",
                (search_id,),
            )
        return row
