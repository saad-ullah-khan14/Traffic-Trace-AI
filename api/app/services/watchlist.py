"""Is this newly seen vehicle one we are already looking for?

Runs on every new sighting, not just violations — that is the whole point. A
vehicle that fled a violation at camera A is an ordinary passing vehicle when it
reaches camera C, and nothing would flag it unless we checked every one.

Alerts are stored as matches on the existing incident, so an officer reviews a
reappearance through exactly the same screen as any other candidate.
"""

import logging
from typing import Any
from uuid import UUID

from app.db.queries import matches as matches_q
from app.services.geo import haversine_meters, is_reachable
from app.services.matching import _as_list
from app.services.pipeline_client import check_watchlist

logger = logging.getLogger(__name__)


def _payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "sighting_id": str(row["sighting_id"]),
        "camera_id": str(row["camera_id"]),
        "ts": row["ts"].isoformat(),
        "vehicle_type": row.get("vehicle_type"),
        "veh_emb": _as_list(row.get("veh_emb")),
        "rider_emb": _as_list(row.get("rider_emb")),
        "attrs": row.get("attrs") or {},
    }


def check_sighting(conn, sighting, camera, open_incidents, cameras) -> list[dict[str, Any]]:
    """Compare one new sighting against every open incident.

    Returns the alerts that crossed his threshold, already saved as matches.
    """
    if not open_incidents:
        return []

    by_id = {c["id"]: c for c in cameras}
    new_payload = _payload({**sighting, "sighting_id": sighting["id"]})

    incident_payloads = []
    for incident in open_incidents:
        # A sighting cannot be a reappearance of itself.
        if incident["sighting_id"] == sighting["id"]:
            continue

        # Nor is "seen again at the same camera" evidence of anything. With
        # distance 0 the space-time signal returns a free 1.0, which alone lifts
        # the minimum achievable score to 0.609 — above the 0.6 alert threshold.
        # Measured, that meant every open incident alerted on every passing
        # vehicle: 20 open incidents produced 20 toasts and ~20 match rows per
        # sighting. Skipping same-camera pairs restores the threshold: a true
        # match over a real hop scores 0.758, a different vehicle 0.546.
        if incident["camera_id"] == sighting["camera_id"]:
            continue

        # Plausibility is a FILTER here, not a score. Sending distance and time
        # to the scorer makes space-time 35% of an identity judgement, and
        # measured on real footage it points the wrong way: a different bike
        # arriving at a comfortable pace scored 0.79 on it while the true match,
        # crossing a short hop quickly, scored 0.51. So reachability decides
        # whether to ask the question at all, and appearance answers it.
        other_camera = by_id.get(incident["camera_id"])
        distance_m = (
            haversine_meters(camera["lat"], camera["lng"], other_camera["lat"], other_camera["lng"])
            if other_camera
            else 0.0
        )
        gap_seconds = abs((sighting["ts"] - incident["ts"]).total_seconds())
        if not is_reachable(distance_m, gap_seconds):
            continue

        incident_payloads.append(
            {
                **_payload(incident),
                "incident_id": str(incident["incident_id"]),
            }
        )

    alerts = check_watchlist(new_payload, incident_payloads)

    for alert in alerts:
        matches_q.save_matches(
            conn,
            incident_id=UUID(alert["incident_id"]),
            scored=[(sighting["id"], float(alert["score"]), alert.get("breakdown") or {})],
        )
        logger.info(
            "WATCHLIST HIT: incident %s reappeared at %s, score %.3f",
            alert["incident_id"],
            camera.get("name"),
            alert["score"],
        )

    return alerts
