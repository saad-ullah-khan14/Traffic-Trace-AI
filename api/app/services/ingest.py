"""Turning one frame into sightings, crops and incidents.

The core product rule lives here: **every vehicle is fingerprinted, always.**
A sighting is stored for every detection regardless of whether anything is
wrong. Only detections carrying a violation additionally open an incident.

That ordering is what makes the whole system work — when a violation is found at
camera B, the same vehicle's earlier appearance at camera A is already on record,
because it was stored when nobody had any reason to care about it.

This module stays synchronous and does no broadcasting: it returns the events it
produced and the worker publishes them. Keeping it that way means it can be
called from a thread, and tested without an event loop.
"""

import logging
import numpy as np
import cv2
from pathlib import Path
import time
from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import UUID

from app.db.queries import cameras as cameras_q
from app.db.queries import incidents as incidents_q
from app.db.queries import sightings as sightings_q
from app.services import evidence
from app.services import watchlist as watchlist_service
from app.services.matching import assert_normalized, run_matching
from app.services.pipeline_client import dedupe, process_frame, read_plate

logger = logging.getLogger(__name__)

# How far back dedupe looks for an earlier frame of the same vehicle. A little
# wider than the pipeline's own 3 s burst window, so a burst that straddles the
# boundary still clusters.
DEDUPE_LOOKBACK_SECONDS = 5.0

# How long one violation event at one camera lasts, for the purpose of not
# opening a second incident for it. A bike is in shot for a few seconds at 1 fps,
# and longer if it stops at the light.
#
# ponytail: time-based, not appearance-based, because no visual signal separates
# "the same bike again" from "a different bike" at one camera — measured, both
# CLIP and the colour histogram put frames of ONE bike inside the range two
# different bikes produce. Ceiling: two genuinely different offenders passing the
# same camera inside this window become one incident. Narrow it, or find a signal
# that actually discriminates, if under-counting ever matters more than a queue
# full of duplicates.
INCIDENT_MERGE_WINDOW_SECONDS = 10.0

# Smallest vehicle worth recording, as the height of its box in pixels.
#
# A crop this side of it is a smudge: CLIP resizes everything to 224x224, so a
# 52x68 box of a distant bike is upscaled mush and its embedding means nothing.
# It still occupies a candidate slot and still asks an officer to compare it.
#
# Chosen from real footage rather than guessed. Measured across one session at
# 960px capture width:
#     too far   60, 68, 68, 71 px tall
#     usable   145, 157, 213, 214 px tall
# 96 separates them with room on both sides. It is an absolute pixel count on
# purpose - it measures how much real detail the model receives, which is what
# actually matters, and does not drift with frame size.
MIN_VEHICLE_HEIGHT_PX = 96.0



def _crop_url(crop_path: str | None) -> str | None:
    return f"/evidence/{crop_path}" if crop_path else None


def _box_height(bbox) -> float:
    try:
        return abs(float(bbox[3]) - float(bbox[1]))
    except (TypeError, ValueError, IndexError):
        return 0.0


# --- diagnostic sampling -----------------------------------------------------

SAMPLE_EVERY_SECONDS = 15.0
SAMPLES_DIR = Path(__file__).resolve().parents[3] / "logs" / "frames"
_last_sample: dict[str, float] = {}


def _save_blank_sample(camera_id, ts, frame_bytes: bytes) -> None:
    """Write one frame that produced no detections, so it can be looked at."""
    key = str(camera_id)
    now = time.monotonic()
    if now - _last_sample.get(key, -1e9) < SAMPLE_EVERY_SECONDS:
        return
    _last_sample[key] = now
    try:
        SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
        name = f"{ts:%H%M%S}_{key[:8]}_{len(frame_bytes)}b.jpg"
        (SAMPLES_DIR / name).write_bytes(frame_bytes)
        logger.info(
            "no detections - saved a sample frame to logs/frames/%s (%d bytes)",
            name,
            len(frame_bytes),
        )
    except Exception:
        logger.exception("could not save a diagnostic frame sample")


# --- sideways frames ---------------------------------------------------------
#
# getUserMedia hands back frames in the sensor's orientation. The browser rotates
# the <video> element for display, so the phone looks right while the uploaded
# canvas is sideways. The camera page corrects this using
# screen.orientation.angle — but a phone with auto-rotate LOCKED reports angle 0
# while being held sideways, and then nothing is corrected. Measured 1 Sep: the
# same real frame gave 0 motorcycles as uploaded and 2 (122 px, 169 px) rotated
# 90° counter-clockwise.
#
# So the server does not trust the client's orientation. The first time a camera
# produces nothing, its frame is retried rotated; whichever way works is
# remembered for that camera and used from then on, at no further cost. A camera
# that is simply looking at an empty road never latches, because rotating an
# empty road still finds nothing.
_ROTATIONS = {"ccw": cv2.ROTATE_90_COUNTERCLOCKWISE, "cw": cv2.ROTATE_90_CLOCKWISE}
# How many empty frames in a row before the orientation is questioned again.
# An empty road must not pay for a rotated retry on every single frame, and a
# sideways camera must not wait long to be noticed. Five frames is ~5 seconds.
RETRY_ORIENTATION_EVERY = 5

_camera_rotation: dict[str, str] = {}
_camera_misses: dict[str, int] = {}


def _rotate_jpeg(frame_bytes: bytes, how: str) -> Optional[bytes]:
    """Return the frame rotated, or None if it cannot be decoded."""
    try:
        image = cv2.imdecode(np.frombuffer(frame_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            return None
        ok, buffer = cv2.imencode(".jpg", cv2.rotate(image, _ROTATIONS[how]),
                                  [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        return buffer.tobytes() if ok else None
    except Exception:
        logger.exception("could not rotate a frame")
        return None


def _detect_upright(camera_id, ts, frame_bytes: bytes):
    """process_frame, on whichever orientation this camera actually needs.

    Returns (detections, frame_bytes) — the bytes are the orientation the
    detections belong to, so crops and plate reads use the same picture.

    An earlier version latched "upright is fine" the first time any frame
    produced a detection, and that was wrong: `smoke_demo` posts upright test
    images through these same camera ids, so a camera could be marked upright by
    the test suite and then never question a single sideways frame from a real
    phone again. Nothing is latched on success now — only a *run* of empty frames
    triggers a retry, and only a rotation that actually finds something is kept.
    """
    key = str(camera_id)

    latched = _camera_rotation.get(key)
    if latched:
        turned = _rotate_jpeg(frame_bytes, latched)
        if turned is not None:
            found = process_frame(turned, key, ts)
            if found:
                _camera_misses[key] = 0
                return found, turned
            # The rotation stopped paying off - the phone may have been turned
            # back. Fall through and re-examine from scratch.
            _camera_rotation.pop(key, None)

    detections = process_frame(frame_bytes, key, ts)
    if detections:
        _camera_misses[key] = 0
        return detections, frame_bytes

    misses = _camera_misses.get(key, 0) + 1
    _camera_misses[key] = misses
    if misses % RETRY_ORIENTATION_EVERY:
        return detections, frame_bytes

    for how in _ROTATIONS:
        turned = _rotate_jpeg(frame_bytes, how)
        if turned is None:
            continue
        found = process_frame(turned, key, ts)
        if found:
            _camera_rotation[key] = how
            _camera_misses[key] = 0
            logger.warning(
                "camera %s is uploading sideways frames - rotating every frame "
                "%s from now on. The phone's auto-rotate is probably locked.",
                key,
                how,
            )
            return found, turned

    return detections, frame_bytes


def ingest_frame(
    conn,
    camera_id: UUID,
    ts: datetime,
    frame_bytes: bytes,
) -> dict[str, Any]:
    """Process one frame end to end.

    Returns a summary including `events`: (type, payload) pairs for the worker
    to broadcast. Runs in a worker thread, not in the request, so a slow model
    never blocks a phone's capture loop.
    """
    detections, frame_bytes = _detect_upright(camera_id, ts, frame_bytes)

    # When a camera sends frame after frame and the detector finds nothing in
    # any of them, the counts cannot tell you why: an empty road, a black frame
    # from a camera that never really started, and a bike too small to detect
    # all read as "0 detected". So keep a sample on disk and LOOK at it. A count
    # is not a check — the same lesson the map tiles taught.
    # Rate-limited to one frame per camera per SAMPLE_EVERY_SECONDS, and only
    # when nothing was detected, so a working demo writes nothing at all.
    if not detections:
        _save_blank_sample(camera_id, ts, frame_bytes)

    # Burst dedup. At 1 fps a vehicle stopped at a light produces the same
    # sighting several times over, and those near-identical rows crowd genuinely
    # different vehicles out of the top-20 candidate list an officer reviews.
    # camera_id and ts are attached because dedupe compares on them.
    raw_count = len(detections)

    # Drop anything too small to be worth an officer's attention, before it
    # costs a crop, a row, a watchlist pass and a slot on the review screen.
    too_small = [d for d in detections if _box_height(d["bbox"]) < MIN_VEHICLE_HEIGHT_PX]
    if too_small:
        detections = [d for d in detections if d not in too_small]
        logger.info(
            "%d of %d detections were too small to identify (< %.0f px tall) - "
            "dropped. Heights: %s. A near miss means the camera only has to move "
            "closer; a number far below means the vehicle was never captured.",
            len(too_small),
            raw_count,
            MIN_VEHICLE_HEIGHT_PX,
            ", ".join(f"{_box_height(d['bbox']):.0f}px" for d in too_small),
        )

    if detections:
        recent = sightings_q.get_recent_at_camera(
            conn, camera_id=camera_id, before=ts, window_seconds=DEDUPE_LOOKBACK_SECONDS
        )
        detections = dedupe(
            [{**d, "camera_id": camera_id, "ts": ts} for d in detections], recent
        )
        if len(detections) < raw_count:
            logger.info(
                "dedupe: %d of %d detections were repeats of a frame already stored",
                raw_count - len(detections),
                raw_count,
            )

    # Fetched once per frame, not per detection: the watchlist runs against
    # every vehicle, so a query per sighting would slow ingest as the demo goes on.
    cameras = cameras_q.list_cameras(conn)
    this_camera = next((c for c in cameras if c["id"] == camera_id), None)
    open_incidents = incidents_q.get_open_for_watchlist(conn)

    summary: dict[str, Any] = {
        "detections": raw_count,
        "kept": len(detections),
        "violations": sum(len(d.get("violations") or []) for d in detections),
        "sightings": [],
        "incidents": [],
        "skipped": 0,
        "events": [],
    }

    for detection in detections:
        # Contractually Teammate 1 normalizes inside process_frame. We verify
        # rather than re-normalize: silently fixing it would hide a regression
        # that degrades every match score with no error anywhere.
        assert_normalized(detection["veh_emb"], label=f"veh_emb from camera {camera_id}")

        # The rider goes in the picture too — see save_crop. A car has no rider
        # box, so this is simply empty for anything that is not a motorcycle.
        crop = evidence.save_crop(
            frame_bytes, detection["bbox"], also=detection.get("rider_bboxes")
        )
        if crop is None:
            summary["skipped"] += 1
            continue
        crop_path, crop_hash = crop
        # Phase 4 of FIND_ME_PLAN.md: also keep the whole frame, so a Find Me
        # result or an incident review can show the full scene. Best-effort —
        # None (disk guard, write failure) just means no full frame is shown,
        # same as before this existed.
        frame_path = evidence.save_frame(frame_bytes, camera_id, ts)
        sighting = sightings_q.insert_sighting(
            conn,
            camera_id=camera_id,
            ts=ts,
            vehicle_type=detection["vehicle_type"],
            bbox=detection["bbox"],
            veh_emb=detection["veh_emb"],
            rider_emb=detection.get("rider_emb"),
            attrs=detection.get("attrs") or {},
            confidence=detection.get("confidence"),
            crop_path=crop_path,
            crop_hash=crop_hash,
            violations=detection.get("violations") or [],
            frame_path=frame_path,
        )
        summary["sightings"].append(sighting["id"])

        # Watchlist: is this ordinary passing vehicle one we are already
        # looking for? Runs on EVERY sighting — a vehicle that fled a violation
        # elsewhere is unremarkable by the time it reaches this camera.
        if this_camera is not None:
            stored = {**sighting, "veh_emb": detection["veh_emb"],
                      "rider_emb": detection.get("rider_emb"),
                      "attrs": detection.get("attrs") or {},
                      "vehicle_type": detection["vehicle_type"], "ts": ts}
            alerts = watchlist_service.check_sighting(
                conn, stored, this_camera, open_incidents, cameras
            )
            for alert in alerts:
                summary["events"].append((
                    "match_suggestion",
                    {
                        "incident_id": alert["incident_id"],
                        "sighting_id": str(sighting["id"]),
                        "camera_id": str(camera_id),
                        "camera_name": this_camera.get("name"),
                        "score": alert["score"],
                        "breakdown": alert.get("breakdown") or {},
                        "crop_url": _crop_url(crop_path),
                        "reappearance": True,
                    },
                ))

        summary["events"].append((
            "sighting",
            {
                "id": str(sighting["id"]),
                "camera_id": str(camera_id),
                "ts": ts.isoformat(),
                "vehicle_type": detection["vehicle_type"],
                "confidence": detection.get("confidence"),
                "crop_url": _crop_url(crop_path),
            },
        ))

        violations = detection.get("violations") or []
        # OCR once per detection, not once per violation. A vehicle with two
        # violations shares one plate; running it twice costs a second OCR pass
        # and could store two different plate values for the same vehicle.
        plate = read_plate(frame_bytes, detection["bbox"]) if violations else None

        for violation in violations:
            # One pass of one vehicle is one incident, however many frames of it
            # the helmet model flags. Without this a bike in shot for six seconds
            # opened an incident per flagged frame, and the officer's queue filled
            # with duplicate cards of the same rider.
            already = incidents_q.find_open_at_camera(
                conn,
                camera_id=camera_id,
                violation=violation,
                since=ts - timedelta(seconds=INCIDENT_MERGE_WINDOW_SECONDS),
            )
            if already is not None:
                logger.info(
                    "%s at camera %s already open as incident %s (%.1fs ago) - "
                    "not opening a second",
                    violation,
                    camera_id,
                    already["id"],
                    (ts - already["ts"]).total_seconds(),
                )
                continue

            incident = incidents_q.insert_incident(
                conn,
                sighting_id=sighting["id"],
                violation=violation,
                plate_text=plate,
            )
            summary["incidents"].append(incident["id"])
            summary["events"].append((
                "incident",
                {
                    "id": str(incident["id"]),
                    "sighting_id": str(sighting["id"]),
                    "camera_id": str(camera_id),
                    "violation": violation,
                    "plate_text": plate,
                    "status": incident["status"],
                    "vehicle_type": detection["vehicle_type"],
                    "attrs": detection.get("attrs") or {},
                    "crop_url": _crop_url(crop_path),
                    "created_at": incident["created_at"].isoformat(),
                },
            ))

            logger.info(
                "incident %s: %s at camera %s, plate=%s",
                incident["id"],
                violation,
                camera_id,
                plate or "UNREADABLE (fingerprint mode)",
            )

            # THE PRODUCT BOUNDARY. This system is an upgrade to an existing
            # ANPR deployment, not a replacement for one. A readable plate is
            # already solved: the existing system issues the ticket from the
            # plate alone, and fingerprint matching would add cost and a second
            # opinion nobody asked for.
            #
            # So the expensive half — gating, ranking, scoring, the review queue
            # — runs ONLY when the plate could not be read. That is the blind
            # spot this feature exists to cover.
            #
            # The sighting is still stored either way, and that is not optional:
            # a vehicle whose plate is unreadable at camera C has to be matched
            # against its earlier appearances at A and B, and at the time those
            # were recorded nobody knew it would matter. Fingerprints must exist
            # BEFORE the violation, so they cannot be gated on it.
            if plate:
                logger.info(
                    "incident %s: plate %s read - handed to ANPR, fingerprint "
                    "matching skipped",
                    incident["id"],
                    plate,
                )
                scored = []
            else:
                # Match immediately, so candidates are already waiting when an
                # officer opens the incident seconds later.
                origin = sightings_q.get_sighting(conn, sighting["id"])
                scored = run_matching(conn, incident["id"], origin, cameras) if origin else []

            if scored:
                best = scored[0]
                summary["events"].append((
                    "match_suggestion",
                    {
                        "incident_id": str(incident["id"]),
                        "candidate_count": len(scored),
                        "best_score": best["score"],
                        "breakdown": best["breakdown"],
                    },
                ))
                logger.info(
                    "incident %s: %d candidates, best %.3f",
                    incident["id"],
                    len(scored),
                    best["score"],
                )

    return summary
