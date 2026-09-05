"""
Phase 13 — Journey builder.

build_journey(confirmed_sightings) -> dict

Chains officer-confirmed sightings of the SAME vehicle into a time-ordered
route, for the map animation.

NOTE: exact field names here are a reasonable draft based on
pipeline/types.py and the pattern Muhammad has used elsewhere (he
pre-computes geo/time stuff on his side and hands us plain values). This
has NOT been confirmed with Muhammad yet — confirm before sending, the
same way we did for score_candidates.
"""

from datetime import datetime
import math


def _parse_ts(ts):
    """Accepts ISO timestamp strings like '2026-08-22T14:03:11Z'."""
    if isinstance(ts, datetime):
        return ts
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance between two lat/lon points, in km."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def build_journey(confirmed_sightings):
    """
    confirmed_sightings: list[dict], each expected to have at least:
        {
            "sighting_id": str,
            "camera_id": str,
            "ts": str,              # ISO timestamp
            "lat": float,           # camera latitude
            "lon": float,           # camera longitude
            "match_score": float,   # optional — confidence this hop is correct (0-1)
        }
        Order doesn't matter going in — we sort by ts.

    Returns:
        {
            "stops": [
                {
                    "sighting_id": str,
                    "camera_id": str,
                    "ts": str,
                    "lat": float,
                    "lon": float,
                    "hop_confidence": float,   # confidence for the hop INTO this stop (1.0 for the first stop)
                    "hop_distance_km": float,  # distance from previous stop (0.0 for the first stop)
                    "hop_seconds": float,      # time from previous stop (0.0 for the first stop)
                },
                ...
            ],
            "total_span_seconds": float,
            "total_distance_km": float,   # exactly equal to sum(stop["hop_distance_km"])
        }

    Returns None if the input list is empty (nothing to build).
    """
    if not confirmed_sightings:
        return None

    ordered = sorted(confirmed_sightings, key=lambda s: _parse_ts(s["ts"]))

    stops = []
    total_distance_km = 0.0

    for i, sighting in enumerate(ordered):
        if i == 0:
            hop_confidence = 1.0
            hop_distance_km = 0.0
            hop_seconds = 0.0
        else:
            prev = ordered[i - 1]
            hop_confidence = sighting.get("match_score", 1.0)

            if "lat" in sighting and "lon" in prev and "lat" in prev and "lon" in sighting:
                # Round HERE, once, so the per-hop value shown to the officer
                # is exactly what gets summed into total_distance_km below —
                # no drift between the displayed hops and the displayed total.
                hop_distance_km = round(
                    _haversine_km(prev["lat"], prev["lon"], sighting["lat"], sighting["lon"]), 3
                )
            else:
                hop_distance_km = 0.0

            hop_seconds = (_parse_ts(sighting["ts"]) - _parse_ts(prev["ts"])).total_seconds()
            total_distance_km += hop_distance_km  # summing the already-rounded value

        stops.append(
            {
                "sighting_id": sighting["sighting_id"],
                "camera_id": sighting["camera_id"],
                "ts": sighting["ts"],
                "lat": sighting.get("lat"),
                "lon": sighting.get("lon"),
                "hop_confidence": round(hop_confidence, 4),
                "hop_distance_km": hop_distance_km,  # already rounded above
                "hop_seconds": hop_seconds,
            }
        )

    total_span_seconds = (
        (_parse_ts(ordered[-1]["ts"]) - _parse_ts(ordered[0]["ts"])).total_seconds()
        if len(ordered) > 1
        else 0.0
    )

    return {
        "stops": stops,
        "total_span_seconds": total_span_seconds,
        # total_distance_km is a sum of already-rounded hop values, so no
        # further rounding needed here — this exactly matches sum(hops).
        "total_distance_km": round(total_distance_km, 3),
    }


if __name__ == "__main__":
    # Quick manual check with fake data.
    fake_sightings = [
        {"sighting_id": "s1", "camera_id": "cam-A", "ts": "2026-08-22T14:00:00Z",
         "lat": 24.8607, "lon": 67.0011, "match_score": 1.0},
        {"sighting_id": "s2", "camera_id": "cam-B", "ts": "2026-08-22T14:05:00Z",
         "lat": 24.8700, "lon": 67.0100, "match_score": 0.87},
        {"sighting_id": "s3", "camera_id": "cam-C", "ts": "2026-08-22T14:12:00Z",
         "lat": 24.8800, "lon": 67.0200, "match_score": 0.91},
    ]
    import json
    print(json.dumps(build_journey(fake_sightings), indent=2))