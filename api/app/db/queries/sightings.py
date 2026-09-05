"""SQL for the sightings table, including the space-time gate.

The gate is the hot path of the whole system: it narrows every sighting ever
recorded down to the handful a vehicle could physically have produced, before
any similarity maths runs.
"""

import json
from datetime import datetime
from typing import Any, Optional, Sequence
from uuid import UUID

import psycopg

# Full detail, for the handful of rows that survive ranking.
_CANDIDATE_COLUMNS = """
    s.id, s.camera_id, s.ts, s.vehicle_type, s.bbox, s.attrs,
    s.veh_emb, s.rider_emb, s.confidence, s.crop_path, s.crop_hash,
    s.violations
"""

# The gate returns hundreds of rows of which ~20 survive, so it selects only
# what ranking actually needs. Adding bbox and attrs here costs ~25 ms per
# query in JSON parsing for rows that are about to be discarded; the survivors
# are hydrated afterwards by get_sightings_by_ids.
_GATE_COLUMNS = "s.id, s.camera_id, s.ts, s.veh_emb, s.confidence"


def insert_sighting(
    conn: psycopg.Connection,
    camera_id: UUID,
    ts: datetime,
    vehicle_type: str,
    bbox: Sequence[float],
    veh_emb: Sequence[float],
    rider_emb: Optional[Sequence[float]] = None,
    attrs: Optional[dict[str, Any]] = None,
    confidence: Optional[float] = None,
    crop_path: Optional[str] = None,
    crop_hash: Optional[str] = None,
    violations: Optional[Sequence[str]] = None,
    frame_path: Optional[str] = None,
) -> dict[str, Any]:
    """Store one fingerprinted vehicle.

    Embeddings must already be L2-normalized — Teammate 1 owns that inside
    process_frame. Wrong-length vectors are rejected by a CHECK constraint
    rather than silently ranking badly later.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
                INSERT INTO sightings (
                camera_id, ts, vehicle_type, bbox, veh_emb, rider_emb,
                attrs, confidence, crop_path, crop_hash, violations, frame_path
            )
            VALUES (
                %s, %s, %s, %s::jsonb, %s::real[], %s::real[],
                %s::jsonb, %s, %s, %s, %s::text[], %s
            )
            RETURNING id, camera_id, ts, vehicle_type, violations, created_at
            """,
            (
                camera_id,
                ts,
                vehicle_type,
                json.dumps(list(bbox)),
                list(veh_emb),
                list(rider_emb) if rider_emb is not None else None,
                json.dumps(attrs or {}),
                confidence,
                crop_path,
                crop_hash,
                list(violations or []),
                frame_path,
            
            ),
        )
        return cur.fetchone()


def get_sighting(conn: psycopg.Connection, sighting_id: UUID) -> Optional[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {_CANDIDATE_COLUMNS}, s.created_at FROM sightings s WHERE s.id = %s",
            (sighting_id,),
        )
        return cur.fetchone()


def get_gated_candidates(
    conn: psycopg.Connection,
    origin_ts: datetime,
    exclude_sighting_id: UUID,
    camera_ids: Sequence[UUID],
    min_gap_seconds: Sequence[float],
    window_seconds: float,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """The space-time gate.

    Returns sightings that could plausibly be the same vehicle, judged purely on
    where and when — no image data involved. Similarity ranking happens after
    this, in numpy.

    `camera_ids` and `min_gap_seconds` are parallel arrays: for each camera, the
    minimum time gap a vehicle would need to travel there from the origin camera.
    They are computed in app.services.geo from the same speed and grace constants
    that pipeline.is_reachable uses, so both sides agree by construction.

    A candidate qualifies when:
      - it is at one of the given cameras
      - it falls inside the +/- window around the origin timestamp
      - the time gap is at least that camera's minimum travel time

    That last condition is what makes this a *reachability* filter rather than a
    plain time range: a vehicle cannot be 3 km away 4 seconds later.
    """
    if not camera_ids:
        return []

    # binary=True is load-bearing, not a micro-optimisation: it lets the numpy
    # loader in app/db/numpy_types.py read embeddings straight from the wire
    # buffer. In text format psycopg builds ~256,000 Python floats per query,
    # which measured at ~90 ms against an 8 ms query.
    # Two index-ordered scans, one each side of the incident, each taking half
    # the budget.
    #
    # The obvious `ORDER BY s.ts DESC LIMIT n` over a symmetric window is wrong:
    # it keeps only the newest rows and discards everything *before* the
    # incident — exactly the earlier appearance this product exists to find.
    #
    # Ordering by `abs(ts - t0)` fixes that but sorts on a computed expression,
    # which no index can serve, so Postgres sorts every matching row. Splitting
    # into a backward and a forward scan lets both halves ride
    # idx_sightings_camera_ts directly, and guarantees the past is represented.
    half = max(1, limit // 2)

    params = {
        "camera_ids": list(camera_ids),
        "min_gaps": list(min_gap_seconds),
        "exclude_id": exclude_sighting_id,
        "t0": origin_ts,
        "t_start": origin_ts - _seconds(window_seconds),
        "t_end": origin_ts + _seconds(window_seconds),
        "half": half,
    }

    with conn.cursor(binary=True) as cur:
        cur.execute(
            f"""
            WITH gate AS (
                SELECT *
                FROM unnest(%(camera_ids)s::uuid[], %(min_gaps)s::double precision[])
                     AS g(camera_id, min_gap)
            ),
            before_incident AS (
                SELECT {_GATE_COLUMNS}
                FROM sightings s
                JOIN gate ON gate.camera_id = s.camera_id
                WHERE s.id <> %(exclude_id)s
                  AND s.ts >= %(t_start)s AND s.ts <= %(t0)s
                  AND abs(extract(epoch FROM (s.ts - %(t0)s))) >= gate.min_gap
                ORDER BY s.ts DESC
                LIMIT %(half)s
            ),
            after_incident AS (
                SELECT {_GATE_COLUMNS}
                FROM sightings s
                JOIN gate ON gate.camera_id = s.camera_id
                WHERE s.id <> %(exclude_id)s
                  AND s.ts > %(t0)s AND s.ts <= %(t_end)s
                  AND abs(extract(epoch FROM (s.ts - %(t0)s))) >= gate.min_gap
                ORDER BY s.ts ASC
                LIMIT %(half)s
            )
            SELECT * FROM before_incident
            UNION ALL
            SELECT * FROM after_incident
            """,
            params,
        )
        return cur.fetchall()


def get_sightings_by_ids(
    conn: psycopg.Connection,
    sighting_ids: Sequence[UUID],
) -> dict[UUID, dict[str, Any]]:
    """Full detail for specific sightings, keyed by id.

    Used to hydrate the ~20 candidates that survive ranking. Doing this after
    ranking rather than before means bbox/attrs JSON is parsed for twenty rows
    instead of several hundred.
    """
    if not sighting_ids:
        return {}

    with conn.cursor(binary=True) as cur:
        cur.execute(
            f"""
            SELECT {_CANDIDATE_COLUMNS},
                   c.name AS camera_name, c.lat, c.lng
            FROM sightings s
            JOIN cameras c ON c.id = s.camera_id
            WHERE s.id = ANY(%s::uuid[])
            """,
            (list(sighting_ids),),
        )
        return {row["id"]: row for row in cur.fetchall()}


def get_recent_at_camera(
    conn: psycopg.Connection,
    camera_id: UUID,
    before: datetime,
    window_seconds: float,
) -> list[dict[str, Any]]:
    """Sightings from this camera in the seconds just before `before`.

    Feeds pipeline.dedupe, which collapses a burst of near-identical frames of
    one stationary vehicle down to its best shot. Served entirely by the
    existing (camera_id, ts DESC) index.
    """
    with conn.cursor(binary=True) as cur:
        cur.execute(
            """
            SELECT s.id, s.camera_id, s.ts, s.veh_emb, s.confidence
            FROM sightings s
            WHERE s.camera_id = %s AND s.ts < %s AND s.ts >= %s
            ORDER BY s.ts DESC
            """,
            (camera_id, before, before - _seconds(window_seconds)),
        )
        return cur.fetchall()


def count_sightings(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM sightings")
        return cur.fetchone()["n"]


def _seconds(value: float):
    from datetime import timedelta

    return timedelta(seconds=value)
_SEARCH_COLUMNS = """
    s.id, s.camera_id, s.ts, s.veh_emb, s.rider_emb, s.attrs,
    s.vehicle_type, s.confidence, s.crop_path, s.crop_hash, s.frame_path,
    c.name AS camera_name, c.lat, c.lng
"""


def search_sightings(
    conn,
    from_ts=None,
    to_ts=None,
    camera_ids=None,
    vehicle_type: str | None = None,
    limit: int = 2000,
) -> list[dict]:
    """Plain SQL narrow for Find Me search — time/camera/type filters only,
    no reachability math, no embedding math. Ranking happens after this, in
    numpy (matching.rank_by_cosine). Same SQL-narrows-then-numpy-ranks
    pattern as get_gated_candidates, but for an open-ended search rather
    than one incident's reachable cameras.
    """
    conditions = []
    params: dict = {"limit": limit}

    if from_ts is not None:
        conditions.append("s.ts >= %(from_ts)s")
        params["from_ts"] = from_ts
    if to_ts is not None:
        conditions.append("s.ts <= %(to_ts)s")
        params["to_ts"] = to_ts
    if camera_ids:
        conditions.append("s.camera_id = ANY(%(camera_ids)s::uuid[])")
        params["camera_ids"] = list(camera_ids)
    if vehicle_type:
        conditions.append("s.vehicle_type = %(vehicle_type)s")
        params["vehicle_type"] = vehicle_type

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    with conn.cursor(binary=True) as cur:
        cur.execute(
            f"""
            SELECT {_SEARCH_COLUMNS}
            FROM sightings s
            JOIN cameras c ON c.id = s.camera_id
            {where_clause}
            ORDER BY s.ts DESC
            LIMIT %(limit)s
            """,
            params,
        )
        return cur.fetchall()
