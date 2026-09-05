"""Building the route a vehicle took, from officer-confirmed sightings.

This is the demo's closing image: a violation at one camera, then the same
vehicle appearing at two more, drawn as a line across the map. It only ever
contains sightings a human confirmed — nothing here is inferred automatically.
"""

import logging
from typing import Any, Optional
from uuid import UUID

from app.db.queries import incidents as incidents_q
from app.db.queries import journeys as journeys_q
from app.db.queries import matches as matches_q
from app.services.pipeline_client import build_journey

logger = logging.getLogger(__name__)


def _to_pipeline_shape(row: dict[str, Any]) -> dict[str, Any]:
    """Our column names -> the names his build_journey expects.

    He uses `lon` and `match_score`; our rows carry `lng` and `score`. Mapping
    here was cheaper than a round-trip asking him to rename, and it keeps the
    difference in one visible place.
    """
    return {
        "sighting_id": str(row["sighting_id"]),
        "camera_id": str(row["camera_id"]),
        "ts": row["ts"].isoformat(),
        "lat": row["lat"],
        "lon": row["lng"],
        "match_score": float(row.get("score") or 1.0),
    }


def _one_stop_per_visit(stops: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse a run of confirmed sightings at one camera into a single stop.

    A vehicle passing a camera at 1 fps produces several sightings, and an officer
    reviewing the candidate list confirms more than one of them — correctly, they
    really are the same vehicle. Left alone, each becomes its own journey stop, so
    a clean A -> B -> C route renders as nine stops, six of which sit on top of one
    another with a 0.0 km hop. On the map that is a three-point line with a stuttering
    animation and a stop list nobody can read.

    Only *consecutive* same-camera stops are merged, so a vehicle that leaves and
    later returns to a camera still gets both visits. The highest-scoring sighting
    in each run is kept: it is the strongest evidence for that hop, and at 1 fps its
    timestamp is within a second or two of the others anyway.
    """
    ordered = sorted(stops, key=lambda s: s["ts"])

    collapsed: list[dict[str, Any]] = []
    for stop in ordered:
        if collapsed and collapsed[-1]["camera_id"] == stop["camera_id"]:
            if (stop.get("score") or 0.0) > (collapsed[-1].get("score") or 0.0):
                # Keep the better evidence, but the arrival time of the visit.
                stop = {**stop, "ts": collapsed[-1]["ts"]}
                collapsed[-1] = stop
            continue
        collapsed.append(stop)

    return collapsed


def rebuild_journey(conn, incident_id: UUID) -> Optional[dict[str, Any]]:
    """Recompute and store the journey for an incident.

    Called after every confirm, so the route grows a hop at a time — which is
    exactly what the map animation shows.

    The originating violation is always the first stop: the journey starts
    where the offence happened, not at the first confirmed match.
    """
    incident = incidents_q.get_incident(conn, incident_id)
    if incident is None:
        return None

    stops = [
        {
            "sighting_id": incident["sighting_id"],
            "camera_id": incident["camera_id"],
            "ts": incident["ts"],
            "lat": incident["lat"],
            "lng": incident["lng"],
            "camera_name": incident.get("camera_name"),
            "crop_path": incident.get("crop_path"),
            "score": 1.0,  # the violation itself is certain, not a match
        }
    ]
    stops.extend(matches_q.get_confirmed_sightings(conn, incident_id))
    stops = _one_stop_per_visit(stops)

    if len(stops) < 2:
        # One stop is a violation, not a journey. Nothing to draw yet.
        return None

    journey = build_journey([_to_pipeline_shape(s) for s in stops])
    if not journey or not journey.get("stops"):
        logger.warning("build_journey returned nothing for incident %s", incident_id)
        return None

    journeys_q.save_journey(
        conn,
        incident_id=incident_id,
        sighting_ids=[UUID(stop["sighting_id"]) for stop in journey["stops"]],
    )

    # Crops are what make the route readable on the map, and his function has
    # no reason to know about them — attach them on the way out.
    crops = {str(s["sighting_id"]): s.get("crop_path") for s in stops}
    # Only rows that actually carry a name contribute, so a row without one
    # cannot overwrite a good name with None.
    names = {
        str(s["camera_id"]): s["camera_name"] for s in stops if s.get("camera_name")
    }

    for stop in journey["stops"]:
        crop = crops.get(stop["sighting_id"])
        stop["crop_url"] = f"/evidence/{crop}" if crop else None
        stop["camera_name"] = names.get(stop["camera_id"])

    journey["incident_id"] = str(incident_id)
    return journey


def get_journey(conn, incident_id: UUID) -> Optional[dict[str, Any]]:
    """Stored journey, rebuilt so hop distances and confidences are present.

    The table holds only the ordered sighting ids; everything else is derived,
    so there is one source of truth and no stale copy to keep in step.
    """
    stored = journeys_q.get_journey(conn, incident_id)
    if stored is None:
        return None
    return rebuild_journey(conn, incident_id)
