"""Distance and reachability.

⚠️ These formulas must stay identical to pipeline.is_reachable. The SQL gate and
Teammate 1's Python check both derive from MAX_SPEED_KMH and GRACE_SECONDS in
app.core.constants; if the two implementations drift, the gate hands the scorer
candidates it was never designed to see and the failure is silent.
"""

import math
from typing import Any, Sequence

from app.core.constants import (
    GATE_MAX_REQUIRED_GAP_SECONDS,
    GRACE_SECONDS,
    MAX_SPEED_KMH,
)

EARTH_RADIUS_M = 6_371_000.0


def haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in metres.

    Straight-line, not road distance — which makes the gate deliberately
    permissive: real roads are longer, so a vehicle needs at least this long.
    Being generous here is correct; the gate should never exclude a true match,
    only the obviously impossible.
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)

    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def min_travel_seconds(distance_m: float) -> float:
    """Fastest possible trip over this distance, minus the grace period.

    Never negative: two cameras metres apart impose no minimum gap.

    Capped by GATE_MAX_REQUIRED_GAP_SECONDS when that is set — a bench-testing
    override so one person with three phones does not have to wait two minutes
    between cameras. See the constant for what it costs.
    """
    seconds_at_max_speed = distance_m / (MAX_SPEED_KMH * 1000.0 / 3600.0)
    required = max(0.0, seconds_at_max_speed - GRACE_SECONDS)

    if GATE_MAX_REQUIRED_GAP_SECONDS is None:
        return required
    return min(required, float(GATE_MAX_REQUIRED_GAP_SECONDS))


def is_reachable(distance_m: float, time_gap_seconds: float) -> bool:
    """Could a vehicle cover this distance in this time gap?

    Mirrors pipeline.is_reachable. Uses the absolute gap, so it holds whether
    the candidate sighting came before or after the incident.
    """
    return abs(time_gap_seconds) >= min_travel_seconds(distance_m)


def build_gate(
    origin_lat: float,
    origin_lng: float,
    cameras: Sequence[dict[str, Any]],
    origin_camera_id: Any = None,
) -> tuple[list[Any], list[float]]:
    """Per-camera minimum travel times, ready for the SQL gate.

    Returns two parallel arrays — camera ids and their minimum gaps in seconds —
    which get passed straight into get_gated_candidates.

    **The origin camera is excluded.** It used to be included with a zero minimum
    gap, on the reasoning that a vehicle circling back is a legitimate match.
    Measured, that was badly wrong: for a same-camera pair the distance is 0, so
    pipeline._space_time_score computes a required speed of 0 km/h and returns a
    free 1.0 on the heaviest-weighted signal (0.35) at any time gap. An unrelated
    bike that passed the same camera two minutes later then outscores the genuine
    cross-camera match and can push it off the top-20 review screen entirely.

    Space-time carries no information about a same-camera pair — everything is
    reachable from where it already is — so the honest thing is to not ask.

    Cost: a vehicle that leaves and returns to one camera is no longer matched.
    That is a real limitation, not a demo one (the demo is A -> B -> C), and it is
    worth far less than a correct ranking. The root fix belongs in
    pipeline/matcher.py, where distance_m == 0 should score neutral rather than
    perfect — raised with Teammate 1.
    """
    camera_ids: list[Any] = []
    min_gaps: list[float] = []

    for camera in cameras:
        if camera["id"] == origin_camera_id:
            continue

        distance = haversine_meters(origin_lat, origin_lng, camera["lat"], camera["lng"])
        camera_ids.append(camera["id"])
        min_gaps.append(min_travel_seconds(distance))

    return camera_ids, min_gaps
