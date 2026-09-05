"""Visual similarity ranking — what replaces pgvector.

The flow, and the division of labour agreed at Checkpoint A:

    SQL gate        narrow every sighting to the physically plausible ones
    numpy cosine    rank those by appearance          <- this module
    score_candidates  fuse the remaining signals      <- Teammate 1

Embeddings arrive already L2-normalized from process_frame, so cosine
similarity is a plain dot product and the whole candidate set is ranked with a
single matrix-vector multiply. On a few hundred candidates this is microseconds;
an index would cost more to maintain than it saves.
"""

import logging
from typing import Any, Optional, Sequence

import numpy as np

from app.core.constants import BURST_WINDOW_SECONDS, CANDIDATE_TOP_K, EMBEDDING_DIM, NORM_TOLERANCE
from app.core.constants import MIN_CANDIDATE_SCORE

logger = logging.getLogger(__name__)


def assert_normalized(embedding: Sequence[float], label: str = "embedding") -> float:
    """Check an embedding is unit length; warn loudly if not. Returns the norm.

    We verify instead of re-normalizing on purpose. Teammate 1 owns
    normalization inside process_frame. If we silently re-normalized here and his
    side ever stopped, ranking quality would degrade with no error anywhere —
    the worst kind of bug to hit during a demo. A warning in the log is findable.
    """
    norm = float(np.linalg.norm(np.asarray(embedding, dtype=np.float32)))
    if abs(norm - 1.0) > NORM_TOLERANCE:
        logger.warning(
            "%s is not L2-normalized (norm=%.6f). pipeline.process_frame is "
            "contractually responsible for normalization.",
            label,
            norm,
        )
    return norm


def rank_by_cosine(
    query_embedding: Sequence[float],
    candidates: Sequence[dict[str, Any]],
    top_k: int = CANDIDATE_TOP_K,
    embedding_field: str = "veh_emb",
) -> list[tuple[dict[str, Any], float]]:
    """Rank gated candidates by visual similarity, best first.

    Returns (candidate, similarity) pairs. Similarity is in [-1, 1]; for
    normalized CLIP embeddings of real vehicles it sits roughly in [0, 1].

    Candidates missing an embedding are skipped rather than scored as zero — a
    missing fingerprint is absent data, not evidence of dissimilarity.
    """
    # Explicit None/length check rather than truthiness: embeddings arrive as
    # numpy arrays from the binary loader, and `if array` raises.
    usable = [
        c for c in candidates
        if c.get(embedding_field) is not None and len(c[embedding_field]) > 0
    ]
    if not usable:
        return []

    query = np.asarray(query_embedding, dtype=np.float32)
    if query.shape[0] != EMBEDDING_DIM:
        raise ValueError(
            f"query embedding has {query.shape[0]} dimensions, expected {EMBEDDING_DIM}"
        )

    matrix = np.asarray([c[embedding_field] for c in usable], dtype=np.float32)

    # Both sides are unit vectors, so the dot product IS the cosine similarity.
    scores = matrix @ query

    k = min(top_k, len(usable))
    # argpartition finds the top k without sorting everything, then we sort only
    # those k. Irrelevant at 500 candidates, correct at 500,000.
    top_idx = np.argpartition(-scores, k - 1)[:k]
    top_idx = top_idx[np.argsort(-scores[top_idx])]

    return [(usable[int(i)], float(scores[int(i)])) for i in top_idx]


def find_candidates(
    conn,
    origin_sighting: dict[str, Any],
    cameras: Sequence[dict[str, Any]],
    window_seconds: Optional[float] = None,
    top_k: int = CANDIDATE_TOP_K,
) -> list[tuple[dict[str, Any], float]]:
    """Full pipeline: space-time gate, then visual ranking.

    Returns the top-K, already ranked — exactly what pipeline.score_candidates
    expects to receive (option (b), agreed at Checkpoint A).

    `origin_sighting` must include id, ts, camera_id and veh_emb; `cameras` is
    the full camera list, which is small enough to pass around directly.
    """
    from app.core.constants import MATCH_WINDOW_SECONDS
    from app.db.queries import sightings as sightings_q
    from app.services.geo import build_gate

    origin_camera = next(
        (c for c in cameras if c["id"] == origin_sighting["camera_id"]), None
    )
    if origin_camera is None:
        raise ValueError(f"camera {origin_sighting['camera_id']} not found")

    camera_ids, min_gaps = build_gate(
        origin_camera["lat"],
        origin_camera["lng"],
        cameras,
        origin_camera_id=origin_camera["id"],
    )

    gated = sightings_q.get_gated_candidates(
        conn,
        origin_ts=origin_sighting["ts"],
        exclude_sighting_id=origin_sighting["id"],
        camera_ids=camera_ids,
        min_gap_seconds=min_gaps,
        window_seconds=window_seconds or MATCH_WINDOW_SECONDS,
    )

    # Before ranking, not after: duplicates of one pass were eating the top-K
    # slots that distinct vehicles should have had.
    collapsed = collapse_bursts(gated)
    if len(collapsed) < len(gated):
        logger.info(
            "burst dedupe: %d sightings -> %d passes", len(gated), len(collapsed)
        )

    ranked = rank_by_cosine(origin_sighting["veh_emb"], collapsed, top_k=top_k)
    if not ranked:
        return []

    # Only now fetch the expensive columns, and only for the survivors.
    full = sightings_q.get_sightings_by_ids(conn, [row["id"] for row, _ in ranked])
    return [(full.get(row["id"], row), score) for row, score in ranked]


# ---------------------------------------------------------------------------
# Phase 11: hand the ranked candidates to Teammate 1's score_candidates
# ---------------------------------------------------------------------------


def _as_list(value):
    """Embeddings arrive as numpy arrays from the binary loader; his code and
    JSON both want plain lists."""
    return None if value is None else (value.tolist() if hasattr(value, "tolist") else list(value))


def collapse_bursts(gated):
    """One vehicle passing one camera once is ONE candidate, not three.

    A camera sampling ~1 fps sees the same bike in two or three consecutive
    frames, and each frame was becoming its own card. The officer was asked the
    same question twice about the same photograph.

    Measured on the 31 Aug run — 9 sightings, 4 real passes:

        same pass, same camera        gap 1-2 s        veh cosine 0.850 - 0.943
        different pass, same camera   gap 120-346 s    veh cosine 0.691 - 0.889

    The cosines OVERLAP, so an embedding threshold cannot tell a burst from a
    second bike; pipeline/dedupe.py's 0.95 would have collapsed nothing, and any
    value low enough to work would merge different riders. This is the same wall
    HANDOFF section 4 hit twice. The time gaps do not overlap at all — two orders
    of magnitude apart — so grouping is on time alone, exactly as
    INCIDENT_MERGE_WINDOW_SECONDS already does for incidents.

    Keeps the highest-confidence frame of each burst, which is also the clearest
    crop, so the officer compares the best available picture rather than the
    first one that arrived.

    ponytail: two different bikes past one camera inside BURST_WINDOW_SECONDS
    collapse into one candidate. A tracker is the real answer, but at ~1.2 fps
    with dropped frames there is no continuity to track.
    """
    kept, best, last_ts = [], None, None
    for row in sorted(gated, key=lambda r: (str(r["camera_id"]), r["ts"])):
        same_burst = (
            best is not None
            and str(row["camera_id"]) == str(best["camera_id"])
            and (row["ts"] - last_ts).total_seconds() <= BURST_WINDOW_SECONDS
        )
        if same_burst:
            if (row.get("confidence") or 0.0) > (best.get("confidence") or 0.0):
                best = row
        else:
            if best is not None:
                kept.append(best)
            best = row
        last_ts = row["ts"]
    if best is not None:
        kept.append(best)
    return kept


def build_scoring_payload(origin, ranked):
    """Shape the data the way pipeline.score_candidates expects.

    **Space-time is deliberately NOT sent.** It reads as an identity signal and
    is not one: it answers "could a vehicle have got here in time", which the SQL
    gate has already asked and answered before anything reaches this function.
    Scoring it again double-counts the gate, and it carries the heaviest weight
    (0.35) while doing so.

    Measured on real labelled footage, it was not merely redundant, it was
    inverted — a different bike that happened to arrive at a comfortable pace
    scored 0.79 on it, while the true match, arriving quickly over a short hop,
    scored 0.51. The signal rewards dawdling, and it was outvoting colour, which
    is the one signal that actually separates.

        with space-time     true 0.66-0.71   false 0.687-0.692   (overlapping)
        without space-time  true 0.741-0.817 false 0.632-0.638   (+0.103 apart)

    `score_candidates` treats a missing distance as a missing signal and
    redistributes its weight across the three that remain, so omitting the keys
    is all that is needed — no change to pipeline/matcher.py, and the division of
    labour comes out right: the gate owns plausibility, the scorer owns
    appearance.
    """
    incident_payload = {
        "sighting_id": str(origin["id"]),
        "camera_id": str(origin["camera_id"]),
        "ts": origin["ts"].isoformat(),
        "vehicle_type": origin.get("vehicle_type"),
        "veh_emb": _as_list(origin.get("veh_emb")),
        "rider_emb": _as_list(origin.get("rider_emb")),
        "attrs": origin.get("attrs") or {},
    }

    candidate_payloads = []
    for candidate, visual_score in ranked:
        candidate_payloads.append(
            {
                "sighting_id": str(candidate["id"]),
                "camera_id": str(candidate["camera_id"]),
                "ts": candidate["ts"].isoformat(),
                "vehicle_type": candidate.get("vehicle_type"),
                "veh_emb": _as_list(candidate.get("veh_emb")),
                "rider_emb": _as_list(candidate.get("rider_emb")),
                "attrs": candidate.get("attrs") or {},
                "visual_score": visual_score,
            }
        )

    return incident_payload, candidate_payloads


def run_matching(conn, incident_id, origin, cameras):
    """Gate -> rank -> fuse -> store. Returns the saved matches, best first.

    Called from the ingest worker the moment an incident opens, so candidates
    are already waiting by the time an officer opens the incident.
    """
    from uuid import UUID

    from app.db.queries import matches as matches_q
    from app.services.pipeline_client import score_candidates

    ranked = find_candidates(conn, origin, cameras)
    if not ranked:
        return []

    incident_payload, candidate_payloads = build_scoring_payload(origin, ranked)
    scored = score_candidates(incident_payload, candidate_payloads)

    # Fall back to our own visual ranking if his scorer returns nothing, so an
    # empty result is a degraded review screen rather than a blank one.
    if not scored:
        logger.warning("score_candidates returned nothing; falling back to visual ranking")
        scored = [
            {
                "sighting_id": str(c["id"]),
                "score": float(v),
                "breakdown": {"vehicle": round(float(v), 4)},
            }
            for c, v in ranked
        ]

    # Store every score, offer only the ones worth asking about. The cut lives in
    # get_matches_for_incident, not here: a candidate dropped at write time is
    # gone, and "the screen was empty" then cannot tell us whether the true match
    # scored 0.69 or was never a candidate at all. Same screen, measurable after.
    below = [m for m in scored if float(m.get("score") or 0.0) < MIN_CANDIDATE_SCORE]
    if below:
        logger.info(
            "incident %s: %d of %d candidates below %.2f (stored, not offered): %s",
            incident_id,
            len(below),
            len(scored),
            MIN_CANDIDATE_SCORE,
            ", ".join(f"{float(m['score']):.3f}" for m in below),
        )

    matches_q.save_matches(
        conn,
        incident_id=incident_id,
        scored=[
            (UUID(row["sighting_id"]), float(row["score"]), row.get("breakdown") or {})
            for row in scored
        ],
    )

    return sorted(scored, key=lambda r: r["score"], reverse=True)


def refresh_candidates(conn, incident) -> None:
    """Re-rank an incident against everything recorded since it opened.

    Matching runs once at ingest so candidates are waiting when the officer
    arrives. But at that instant the vehicle's LATER appearances do not exist
    yet — a bike that passes camera A at 19:46 and camera C at 19:49 leaves
    nothing at C to match when the incident opens at 19:46.

    The watchlist partly covers this, but only for sightings that clear its 0.6
    alert threshold; a genuine match scoring 0.55 never reaches the review
    screen at all. Measured on real footage: the camera A incident collected 4
    candidates while 8 motorcycle sightings existed, and its route stopped at
    two stops because the third camera's sighting was never offered.

    So the review screen re-asks the question when it is opened. save_matches is
    an upsert that never overwrites a decision, so re-running is safe and
    idempotent — already-confirmed candidates keep their decision, and anything
    new simply appears.

    Only for plate-less incidents: a plate that was read is ANPR's business.
    """
    if incident.get("plate_text"):
        return

    from app.db.queries import cameras as cameras_q
    from app.db.queries import sightings as sightings_q

    origin = sightings_q.get_sighting(conn, incident["sighting_id"])
    if origin is None:
        return

    run_matching(conn, incident["id"], origin, cameras_q.list_cameras(conn))
