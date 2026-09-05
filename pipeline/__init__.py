"""
pipeline package — exposes the 7 functions Muhammad's backend calls.

All 7 are REAL implementations as of Phase 15:
    process_frame    — Phase 6
    is_reachable      — Phase 10
    read_plate        — Phase 8
    score_candidates  — Phase 9
    check_watchlist   — Phase 12
    build_journey     — Phase 13
    dedupe            — Phase 14
"""

from pipeline.orchestrator import process_frame
from pipeline.matcher import score_candidates, check_watchlist
from pipeline.alpr import read_plate
from pipeline.journey import build_journey
from pipeline.dedupe import dedupe


def is_reachable(distance_meters, dt_seconds, max_kmh=60, grace_seconds=30):
    """
    Could a vehicle travel `distance_meters` in `dt_seconds`, at up to
    `max_kmh`, allowing a grace period (traffic lights, parking, imprecise
    camera clocks)? Matches the agreed contract with Muhammad: 60 km/h
    max, 30-second grace.
    """
    if dt_seconds < 0:
        return distance_meters <= 0
    effective_seconds = dt_seconds + grace_seconds
    max_mps = (max_kmh * 1000) / 3600  # km/h -> m/s
    max_distance = max_mps * effective_seconds
    return distance_meters <= max_distance