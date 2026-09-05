"""
Phase 9 — Matching: score fusion.

score_candidates(incident, candidates) -> list[dict]

Combines multiple signals into one final match score per candidate:
    - vehicle embedding similarity (veh_emb cosine)
    - rider embedding similarity (rider_emb cosine, if both present)
    - attribute overlap (color_histogram intersection)
    - space-time plausibility (from candidate['distance_m'] / ['time_gap_seconds'])

IMPORTANT (per our own Phase 5 testing + Muhammad's confirmation on his
data): CLIP's vehicle embedding alone is a weak identity signal — different
vehicles sometimes score HIGHER than the same vehicle. So veh_emb gets a
LOWER weight here, and color_histogram + space_time get MORE weight. This
isn't a guess — it's a direct response to measured similarity results.
"""

import numpy as np

# UPDATED 31 Aug 2026, after real-footage measurement (fingerprint upgrade
# brief): vehicle embedding now uses the UNION crop (vehicle+rider), which
# measured margin +0.018 / rank-1 2/2 vs the old fused score's -0.066 / 1/2.
# Colour histogram measured margin -0.364 on real footage — worse than
# useless, actively misleading (grey scenes: grey road, grey light, dark
# clothes). Its weight is cut hard, not removed entirely, since we only
# have 2 confirmed cross-camera pairs so far — full removal is premature
# until more labels exist.
WEIGHT_VEHICLE = 0.45      # union-crop embedding — now the strongest measured signal
WEIGHT_RIDER = 0.25        # rider-only crop, separate signal
WEIGHT_ATTRIBUTES = 0.05   # color histogram — measured harmful, minimal weight kept
WEIGHT_SPACE_TIME = 0.25   # kept, but API doesn't currently send distance/time (dead weight in practice per brief)

MAX_PLAUSIBLE_KMH = 60  # matches the agreed contract with Muhammad
GRACE_SECONDS = 30      # matches the agreed contract with Muhammad

# Watchlist alert threshold — a named constant so it's easy to tune before
# the demo without touching the function logic.
WATCHLIST_ALERT_THRESHOLD = 0.6


def _cosine_sim(a, b):
    """Both inputs are already L2-normalized, so this is just a dot product."""
    if a is None or b is None:
        return None
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b))


def _hist_overlap(h1, h2):
    """Histogram intersection: 1.0 = identical color distribution, 0.0 = totally different."""
    if h1 is None or h2 is None:
        return 0.0
    h1, h2 = np.array(h1), np.array(h2)
    return float(np.sum(np.minimum(h1, h2)))


def _space_time_score(distance_m, time_gap_seconds):
    """
    Returns a float in [0,1], or None when space-time doesn't give a
    meaningful signal — e.g. same-camera candidates (distance_m == 0),
    which would otherwise ALWAYS score 1.0 regardless of time gap and
    unfairly dominate the fused score (found and confirmed by Muhammad's
    testing). None is treated as a missing signal by score_candidates(),
    which redistributes its weight to the other available signals.
    """
    if time_gap_seconds is None or distance_m is None:
        return None
    if distance_m == 0:
        return None
    if time_gap_seconds < 0:
        return 1.0 if distance_m <= 0 else 0.0

    effective_time = time_gap_seconds + GRACE_SECONDS
    required_kmh = (distance_m / 1000) / (effective_time / 3600)
    if required_kmh > MAX_PLAUSIBLE_KMH:
        return 0.0
    return max(0.0, 1.0 - (required_kmh / MAX_PLAUSIBLE_KMH))


# The passenger-count filter is written and tested, and it is DISABLED, because
# the count it reads is not yet trustworthy. Measured 31 Aug across 27 real
# sightings: 24 read 1, two read 0 (a motorcycle with no rider — a detection
# failure, not an empty bike) and one read 3. A bike carrying a child and a
# pillion passenger was recorded as 1.
#
# A hard filter on an ~11%-unreliable signal deletes a true match permanently and
# invisibly, and no benchmark catches it: on the 12 labelled cross-camera pairs
# the filter fires ZERO times, because both sides read 1 in every pair.
#
# Turn this on the day rider_count is measured against the crops and the 0s are
# gone. The idea is right — a one-rider bike and a three-rider bike are not the
# same vehicle — the input is not ready.
PASSENGER_FILTER_ENABLED = False


def _passenger_count_plausible(incident_count, candidate_count):
    """
    Hard filter, not a weighted signal — a one-rider bike and a three-rider
    bike are never the same vehicle, regardless of how similar they look
    visually. Per Phase D1 of the fingerprint upgrade brief: counts can be
    off by small detection errors (occluded pillion riders), so we allow a
    difference of 1, not an exact match.
    """
    if incident_count is None or candidate_count is None:
        return True  # missing data — don't filter, let other signals decide
    return abs(incident_count - candidate_count) <= 1


def score_candidates(incident, candidates):
    """
    incident: dict with veh_emb, rider_emb, attrs (see Muhammad's contract).
    candidates: list of dicts, each incident's fields PLUS visual_score,
                distance_m, time_gap_seconds (Muhammad's SQL/ranking side).

    Returns: list[dict] — one per candidate:
        {
            "sighting_id": str,
            "score": float,
            "breakdown": {"vehicle": float, "rider": float, "attributes": float, "space_time": float},
        }
    """
    incident_veh_emb = incident.get("veh_emb")
    incident_rider_emb = incident.get("rider_emb")
    incident_hist = (incident.get("attrs") or {}).get("color_histogram")
    incident_attrs = incident.get("attrs") or {}
    incident_passenger_count = incident_attrs.get("passenger_count")

    results = []
    for cand in candidates:
        cand_attrs = cand.get("attrs") or {}
        cand_passenger_count = cand_attrs.get("passenger_count")

        if PASSENGER_FILTER_ENABLED and not _passenger_count_plausible(
            incident_passenger_count, cand_passenger_count
        ):
            # Hard reject — skip this candidate entirely, don't even score it.
            results.append(
                {
                    "sighting_id": cand["sighting_id"],
                    "score": 0.0,
                    "breakdown": {"vehicle": 0.0, "rider": 0.0, "attributes": 0.0, "space_time": 0.0},
                }
            )
            continue

        veh_sim = _cosine_sim(incident_veh_emb, cand.get("veh_emb"))
        rider_sim = _cosine_sim(incident_rider_emb, cand.get("rider_emb"))
        attr_score = _hist_overlap(incident_hist, (cand.get("attrs") or {}).get("color_histogram"))
        st_score = _space_time_score(cand.get("distance_m"), cand.get("time_gap_seconds"))

        components = {
            "vehicle": (veh_sim, WEIGHT_VEHICLE),
            "rider": (rider_sim, WEIGHT_RIDER),
            "attributes": (attr_score, WEIGHT_ATTRIBUTES),
            "space_time": (st_score, WEIGHT_SPACE_TIME),
        }
        available = {k: (v, w) for k, (v, w) in components.items() if v is not None}
        total_weight = sum(w for _, w in available.values()) or 1.0

        final_score = sum(v * w for v, w in available.values()) / total_weight
        final_score = max(0.0, min(1.0, final_score))

        breakdown = {
            "vehicle": round(veh_sim, 4) if veh_sim is not None else 0.0,
            "rider": round(rider_sim, 4) if rider_sim is not None else 0.0,
            "attributes": round(attr_score, 4),
            "space_time": round(st_score, 4) if st_score is not None else 0.0,
        }
        results.append(
            {
                "sighting_id": cand["sighting_id"],
                "score": round(final_score, 4),
                "breakdown": breakdown,
            }
        )

    return results


def check_watchlist(new_sighting, open_incidents):
    """
    Phase 12 — Watchlist / live re-detection.

    new_sighting: dict — same shape as score_candidates' `incident` arg.
    open_incidents: list[dict] — same shape as score_candidates' `candidates`,
        PLUS an "incident_id" field on each.

    Returns: list[dict] — one per open incident crossing the alert threshold:
        {"incident_id": str, "sighting_id": str, "score": float, "breakdown": {...}}
    """
    scored = score_candidates(new_sighting, open_incidents)

    incident_id_by_sighting = {
        inc["sighting_id"]: inc["incident_id"] for inc in open_incidents
    }

    alerts = []
    for result in scored:
        if result["score"] >= WATCHLIST_ALERT_THRESHOLD:
            alerts.append(
                {
                    "incident_id": incident_id_by_sighting.get(result["sighting_id"]),
                    "sighting_id": new_sighting["sighting_id"],
                    "score": result["score"],
                    "breakdown": result["breakdown"],
                }
            )

    return alerts


if __name__ == "__main__":
    incident = {
        "sighting_id": "incident-1",
        "veh_emb": [1.0] + [0.0] * 511,
        "rider_emb": [1.0] + [0.0] * 511,
        "attrs": {"color_histogram": [0.5, 0.5, 0, 0, 0, 0, 0, 0]},
    }
    candidates = [
        {
            "sighting_id": "cand-close-match",
            "veh_emb": [0.99] + [0.01] * 511,
            "rider_emb": [0.99] + [0.01] * 511,
            "attrs": {"color_histogram": [0.5, 0.5, 0, 0, 0, 0, 0, 0]},
            "distance_m": 500,
            "time_gap_seconds": 120,
        },
        {
            "sighting_id": "cand-impossible",
            "veh_emb": [0.99] + [0.01] * 511,
            "rider_emb": None,
            "attrs": {"color_histogram": [0.0, 0.0, 0.5, 0.5, 0, 0, 0, 0]},
            "distance_m": 50000,
            "time_gap_seconds": 10,
        },
    ]
    for r in score_candidates(incident, candidates):
        print(r)