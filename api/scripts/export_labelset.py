r"""Export the officer's labels and crops as a self-contained folder.

Teammate 1 has no database, no API and no crops — only `pipeline/`. So the
benchmark that decides whether a new fingerprint model is better has to travel:
a folder of images plus a JSON of labels, runnable with numpy and torch alone.

    cd api
    .\.venv\Scripts\python.exe -m scripts.export_labelset

Writes ../labelset/ :

    crops/          every crop referenced by a pair
    labels.json     the pairs, their labels, and the current model's scores
    benchmark.py    standalone runner — the only thing to edit is embed()
    README.md       what to do with it

Read-only against the database. Re-run it after every labelling session; it
overwrites, and more labels are strictly better.

Two kinds of pair come out of it:

  cross_camera  the real task. One incident's own sighting against a candidate
                at another camera, labelled by the officer on the review screen.
                `confirm` -> same vehicle, `reject` -> different.

  burst         free true pairs. Two frames of ONE pass at ONE camera, gap
                <= BURST_WINDOW_SECONDS. Nobody has to label these — they are
                the same vehicle by construction. They are an easier problem
                than cross-camera and must never be mixed into the headline
                number; they are a floor. A model that cannot separate these
                cannot separate anything.
"""

import json
import shutil
import sys
from itertools import combinations
from pathlib import Path

from app.core.constants import BURST_WINDOW_SECONDS
from app.db.session import get_connection

OUT = Path(__file__).resolve().parents[2] / "labelset"
EVIDENCE = Path(__file__).resolve().parents[2] / "evidence"
KIT = Path(__file__).resolve().parent / "labelset_kit"


def _crop_name(sighting):
    """The file under evidence/ for a sighting, or None when it has no crop."""
    path = sighting.get("crop_path")
    return Path(path).name if path else None


def main() -> int:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT s.id, s.ts, s.camera_id, s.confidence, s.crop_path,
                   c.name AS camera_name
            FROM sightings s JOIN cameras c ON c.id = s.camera_id
            ORDER BY c.name, s.ts
            """
        )
        sightings = {r["id"]: r for r in cur.fetchall()}

        cur.execute(
            """
            SELECT m.incident_id, m.score, m.decision,
                   m.sighting_id AS candidate_id,
                   i.sighting_id AS origin_id
            FROM matches m JOIN incidents i ON i.id = m.incident_id
            WHERE m.decision IS NOT NULL
            ORDER BY m.incident_id, m.score DESC
            """
        )
        decided = cur.fetchall()

    if not decided:
        print("No labelled matches. Open each incident and press "
              "'Same vehicle' / 'Not the same' on every candidate first.")
        return 1

    pairs, needed = [], set()

    for row in decided:
        origin, candidate = sightings.get(row["origin_id"]), sightings.get(row["candidate_id"])
        if origin is None or candidate is None:
            continue
        a, b = _crop_name(origin), _crop_name(candidate)
        if not a or not b:
            continue
        needed.update((a, b))
        pairs.append({
            "kind": "cross_camera",
            "a": a,
            "b": b,
            "same_vehicle": row["decision"] == "confirm",
            "incident": str(row["incident_id"]),
            "baseline_score": round(float(row["score"]), 4),
            "a_camera": origin["camera_name"],
            "b_camera": candidate["camera_name"],
            "gap_seconds": round((candidate["ts"] - origin["ts"]).total_seconds(), 1),
        })

    # Burst pairs: consecutive sightings at one camera inside the window are
    # frames of one pass. Chained, so a bike held in frame stays one group.
    ordered = sorted(sightings.values(), key=lambda s: (s["camera_name"], s["ts"]))
    passes, group = [], []
    for row in ordered:
        if group and row["camera_name"] == group[-1]["camera_name"] \
                and (row["ts"] - group[-1]["ts"]).total_seconds() <= BURST_WINDOW_SECONDS:
            group.append(row)
        else:
            if group:
                passes.append(group)
            group = [row]
    if group:
        passes.append(group)

    for group in passes:
        for x, y in combinations(group, 2):
            a, b = _crop_name(x), _crop_name(y)
            if not a or not b:
                continue
            needed.update((a, b))
            pairs.append({
                "kind": "burst",
                "a": a,
                "b": b,
                "same_vehicle": True,
                "incident": None,
                "baseline_score": None,
                "a_camera": x["camera_name"],
                "b_camera": y["camera_name"],
                "gap_seconds": round((y["ts"] - x["ts"]).total_seconds(), 1),
            })

    # Rank-1 needs the full candidate list per incident, in the order the officer
    # saw it, so a new model can be asked to re-rank the same set.
    incidents = {}
    for row in decided:
        inc = str(row["incident_id"])
        origin, candidate = sightings.get(row["origin_id"]), sightings.get(row["candidate_id"])
        if origin is None or candidate is None:
            continue
        a, b = _crop_name(origin), _crop_name(candidate)
        if not a or not b:
            continue
        entry = incidents.setdefault(inc, {"origin": a, "candidates": []})
        entry["candidates"].append({
            "crop": b,
            "same_vehicle": row["decision"] == "confirm",
            "baseline_score": round(float(row["score"]), 4),
        })

    crops_dir = OUT / "crops"
    if OUT.exists():
        shutil.rmtree(OUT)
    crops_dir.mkdir(parents=True)

    missing = []
    for name in sorted(needed):
        src = EVIDENCE / name
        if src.exists():
            shutil.copy2(src, crops_dir / name)
        else:
            missing.append(name)

    if missing:
        print(f"WARNING: {len(missing)} crop file(s) missing from evidence/ — "
              f"pairs referencing them will fail. First: {missing[0]}")

    cross = [p for p in pairs if p["kind"] == "cross_camera"]
    (OUT / "labels.json").write_text(json.dumps({
        "note": "Generated by api/scripts/export_labelset.py. Labels are the "
                "officer's own decisions on real footage. Do not hand-edit.",
        "burst_window_seconds": BURST_WINDOW_SECONDS,
        "pairs": pairs,
        "incidents": incidents,
    }, indent=2), encoding="utf-8")

    for name in ("benchmark.py", "README.md"):
        shutil.copy2(KIT / name, OUT / name)

    print(f"labelset/ written to {OUT}")
    print(f"  crops           {len(needed) - len(missing)}")
    print(f"  cross-camera    {len(cross)}  "
          f"({sum(p['same_vehicle'] for p in cross)} same, "
          f"{sum(not p['same_vehicle'] for p in cross)} different)")
    print(f"  burst (free)    {len(pairs) - len(cross)}  all same")
    print(f"  incidents       {len(incidents)} with a labelled candidate list")
    print("\nZip the folder and send it. Only benchmark.py's embed() gets edited.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
