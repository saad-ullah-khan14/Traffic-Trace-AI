r"""One pass past one camera must produce one candidate, not three.

Pure function test — no database, no server. Run it from api/:

    .\.venv\Scripts\python.exe -m scripts.test_burst_dedupe

The numbers come from the 31 Aug footage: bursts arrive 1-2 s apart, different
bikes at the same camera 120 s or more apart.
"""

from datetime import datetime, timedelta

from app.services.matching import collapse_bursts

T0 = datetime(2026, 8, 31, 1, 53, 32)


def s(cam, offset_seconds, confidence):
    return {"id": f"{cam}@{offset_seconds}", "camera_id": cam,
            "ts": T0 + timedelta(seconds=offset_seconds), "confidence": confidence}


# The real Camera 1 burst: 3 frames of one bike, 1-2 s apart. The middle frame
# was the clearest, and it is not the one ingest happens to keep.
burst = [s("cam-A", 0, 0.43), s("cam-A", 2, 0.58), s("cam-A", 3, 0.48)]
kept = collapse_bursts(burst)
assert len(kept) == 1, f"one pass must be one candidate, got {len(kept)}"
assert kept[0]["confidence"] == 0.58, "must keep the clearest frame, not the first"

# The real Camera 2 sequence: three separate bikes, minutes apart.
passes = [s("cam-B", 31, 0.44), s("cam-B", 33, 0.59),      # pass 1
          s("cam-B", 152, 0.71), s("cam-B", 155, 0.67),    # pass 2, 2 min later
          s("cam-B", 376, 0.40), s("cam-B", 377, 0.48)]    # pass 3
kept = collapse_bursts(passes)
assert len(kept) == 3, f"three bikes must stay three candidates, got {len(kept)}"
assert [k["confidence"] for k in kept] == [0.59, 0.71, 0.48]

# Two cameras never merge, however close in time.
kept = collapse_bursts([s("cam-A", 0, 0.5), s("cam-B", 1, 0.9)])
assert len(kept) == 2, "different cameras are different sightings"

# A bike held up in frame longer than the window still chains into one pass:
# 0-4-8-12 s, every step inside 5 s, none of them within 5 s of the first.
kept = collapse_bursts([s("cam-A", 0, 0.4), s("cam-A", 4, 0.9),
                        s("cam-A", 8, 0.5), s("cam-A", 12, 0.6)])
assert len(kept) == 1, f"a chained burst is still one pass, got {len(kept)}"
assert kept[0]["confidence"] == 0.9

assert collapse_bursts([]) == []

print("PASS  burst dedupe: 3 frames -> 1 candidate, 3 bikes stay 3, clearest kept")
