"""
Phase 14 — Burst dedup.

dedupe(new_sightings, recent_sightings) -> list[dict]

REWRITTEN 31 Aug 2026 after real-footage measurement (fingerprint upgrade
brief): the original design used embedding similarity (>=0.95) + a time
window to decide duplicates. On real footage this does NOT work — same-pass
cosine measured 0.850-0.943, different-bike cosine measured 0.691-0.889.
Those ranges OVERLAP, so no similarity threshold can separate them (this is
the same CLIP category-vs-identity problem documented in fingerprint.py).

Time, however, separates cleanly: frames from one continuous camera pass are
within a few seconds of each other; a different vehicle at the same camera
is a different pass. So this version dedupes on CAMERA + TIME WINDOW alone,
with NO embedding similarity check.
"""

from datetime import datetime

# 5.0, not 3.0: measured same-pass gaps were 1-2 s and different-bike gaps at
# one camera 120-346 s, so 5 leaves room for a bike held up in traffic without
# coming near a second vehicle. Matches api/app/core/constants.py, which is
# what actually runs today — this module is not wired in.
BURST_WINDOW_SECONDS = 5.0


def _parse_ts(ts):
    if isinstance(ts, datetime):
        return ts
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _same_burst(sighting_a, sighting_b):
    """
    True if two sightings are close enough in time, at the same camera, to
    be considered the same continuous pass. No visual similarity check —
    measured unreliable on real footage (see module docstring).
    """
    if sighting_a.get("camera_id") != sighting_b.get("camera_id"):
        return False
    time_diff = abs(
        (_parse_ts(sighting_a["ts"]) - _parse_ts(sighting_b["ts"])).total_seconds()
    )

    # Two detections from the SAME frame carry the same timestamp, and they are
    # by definition different vehicles — one frame cannot show one bike twice.
    # Time alone cannot tell them apart, so this guard is what the old similarity
    # check was quietly providing. Without it a frame containing three bikes
    # collapses to one sighting: measured 31 Aug, smoke_demo went from 6
    # sightings to 3 and lost the review screen's candidates entirely.
    if time_diff == 0:
        return False

    return time_diff <= BURST_WINDOW_SECONDS


def _quality(sighting):
    """Higher is better. A violation outranks everything else.

    Confidence alone was the proxy, and it silently threw away evidence: within
    one burst the highest-confidence frame is often NOT the one the helmet model
    flagged, so the offence was dropped and the clean frame kept. A sighting that
    carries a violation is the whole reason this system exists — it can never
    lose to a sharper picture of nothing.
    """
    return (bool(sighting.get("violations")), sighting.get("confidence", 0.0))


def dedupe(new_sightings, recent_sightings):
    """
    new_sightings: list[dict] — sightings just produced, each with at least
        camera_id, ts, confidence.
    recent_sightings: list[dict] — sightings already known/stored from the
        last few seconds — used as a reference so we don't re-insert
        something we already have.

    Returns: list[dict] — the subset of new_sightings that should actually
        be kept/inserted, sorted by timestamp. A burst (same camera, within
        BURST_WINDOW_SECONDS) collapses to its single highest-confidence
        sighting. If a burst overlaps a recent_sighting already on record,
        none of the new ones in that burst are kept.

    IMPORTANT CAVEAT: within a tight time window at one camera, this assumes
    at most one vehicle passes — i.e. it will incorrectly merge two DIFFERENT
    vehicles that happen to pass the same camera within 3 seconds of each
    other. This is a real, deliberate tradeoff: similarity-based clustering
    was measured WORSE on real footage (overlapping score ranges). If busy
    intersections make this a frequent problem, the fix is a tighter window
    or a per-lane camera crop, not bringing back embedding similarity.
    """
    if not new_sightings:
        return []

    all_sightings = list(recent_sightings) + list(new_sightings)
    n = len(all_sightings)

    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry

    for i in range(n):
        for j in range(i + 1, n):
            if _same_burst(all_sightings[i], all_sightings[j]):
                union(i, j)

    clusters = {}
    for i in range(n):
        root = find(i)
        clusters.setdefault(root, []).append(all_sightings[i])

    recent_ids = {id(s) for s in recent_sightings}

    kept = []
    for group in clusters.values():
        contains_recent = any(id(s) in recent_ids for s in group)
        if contains_recent:
            continue

        new_members = [s for s in group if id(s) not in recent_ids]
        if new_members:
            best = max(new_members, key=_quality)
            kept.append(best)

    kept.sort(key=lambda s: _parse_ts(s["ts"]))
    return kept


if __name__ == "__main__":
    burst = [
        {"sighting_id": f"s{i}", "camera_id": "cam-A", "ts": f"2026-08-22T14:00:0{i}Z",
         "confidence": 0.7 + i * 0.02}
        for i in range(5)
    ]
    result = dedupe(burst, [])
    print(f"Test 1 — Input: {len(burst)} sightings in a 4s-span burst at one camera")
    print(f"Output: {len(result)} sighting(s) kept")
    for s in result:
        print(f"  {s['sighting_id']} (confidence={s['confidence']})")
    assert len(result) == 1
    assert result[0]["sighting_id"] == "s4"
    print("PASS\n")

    diff_camera = [
        {"sighting_id": "cam1-sighting", "camera_id": "cam-A", "ts": "2026-08-22T14:00:00Z", "confidence": 0.8},
        {"sighting_id": "cam2-sighting", "camera_id": "cam-B", "ts": "2026-08-22T14:00:00Z", "confidence": 0.8},
    ]
    result2 = dedupe(diff_camera, [])
    print(f"Test 2 — Same instant, different cameras")
    print(f"Output: {len(result2)} sighting(s) kept (should be 2)")
    assert len(result2) == 2
    print("PASS\n")

    recent = [{"sighting_id": "old1", "camera_id": "cam-A", "ts": "2026-08-22T14:00:00Z", "confidence": 0.9}]
    new_dup = [{"sighting_id": "new1", "camera_id": "cam-A", "ts": "2026-08-22T14:00:01Z", "confidence": 0.95}]
    result3 = dedupe(new_dup, recent)
    print(f"Test 3 — New sighting within window of an already-recorded recent sighting")
    print(f"Output: {len(result3)} sighting(s) kept (should be 0)")
    assert len(result3) == 0
    print("PASS")