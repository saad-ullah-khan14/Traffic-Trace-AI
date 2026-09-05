r"""Run this BEFORE sending your folder back. It checks your code against the
contract the backend expects.

Run it from the folder that CONTAINS pipeline/ (not from inside it):

    .\.venv\Scripts\python.exe -m pipeline.selftest

If every line says PASS, integration will take minutes. If something says FAIL,
fix it now — the same problem found later costs a whole day, because a mismatch
here produces NO error, just empty results that look like the other person's
bug.

Nothing here needs the database, the API, or a network connection.
"""

import sys
import traceback
from pathlib import Path

# Allow `python pipeline/selftest.py` as well as `python -m pipeline.selftest`,
# by making sure the folder holding pipeline/ is importable either way.
_parent = str(Path(__file__).resolve().parent.parent)
if _parent not in sys.path:
    sys.path.insert(0, _parent)

# ---------------------------------------------------------------------------

results: list[tuple[str, bool, str]] = []


def check(label: str, fn) -> None:
    try:
        ok, note = fn()
    except Exception as exc:
        # Report the message, not a wall of traceback. A missing function is a
        # normal result here, and a beginner should not have to read a stack
        # trace to learn that. Full detail is available with --verbose.
        ok, note = False, f"{type(exc).__name__}: {exc}"
        if "--verbose" in sys.argv:
            traceback.print_exc()
    results.append((label, ok, note))
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {note}" if note else ""))


def make_test_image() -> bytes:
    """A synthetic JPEG, so this runs without any sample footage."""
    import io

    from PIL import Image, ImageDraw

    image = Image.new("RGB", (640, 480), (70, 100, 140))
    draw = ImageDraw.Draw(image)
    draw.rectangle([60, 90, 300, 360], fill=(190, 60, 50))
    draw.rectangle([340, 120, 560, 380], fill=(50, 150, 90))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


def main() -> int:
    print("\nTraffic_Trace — pipeline self-test\n" + "=" * 42)

    # --- 1. can it be imported at all? ------------------------------------
    print("\n[1] import")

    def _import():
        import pipeline  # noqa: F401

        return True, ""

    check("`import pipeline` works", _import)

    # Stop here if the import failed, rather than crashing with a raw traceback
    # that hides the one line that actually explains the problem.
    try:
        import pipeline
    except Exception as exc:
        print("\n" + "=" * 42)
        print(f"  Cannot import pipeline: {exc}")
        print("\n  Check that:")
        print("    - pipeline/__init__.py exists")
        print("    - it exposes process_frame and the other six functions")
        print("    - you ran this from the folder CONTAINING pipeline/, i.e.")
        print("      .\\.venv\\Scripts\\python.exe -m pipeline.selftest")
        return 1

    # --- 2. are all seven functions present? ------------------------------
    print("\n[2] required functions")
    for name in (
        "process_frame",
        "read_plate",
        "score_candidates",
        "is_reachable",
        "check_watchlist",
        "build_journey",
        "dedupe",
    ):
        check(
            f"pipeline.{name} exists",
            lambda n=name: (callable(getattr(pipeline, n, None)), ""),
        )

    # Without process_frame there is nothing further worth testing, and
    # continuing would print a page of confusing follow-on failures.
    if not callable(getattr(pipeline, "process_frame", None)):
        print("\n" + "=" * 42)
        print("  pipeline.process_frame not found — start there.")
        print("\n  Create pipeline/__init__.py containing:")
        print("      from .detect import process_frame")
        print("      from .detect import read_plate")
        print("      ...and the other five")
        print("\n  Re-run this once process_frame exists.")
        return 1

    # --- 3. the shared constant -------------------------------------------
    print("\n[3] shared constant")

    def _dim():
        from pipeline.types import EMBEDDING_DIM

        return EMBEDDING_DIM == 512, f"EMBEDDING_DIM={EMBEDDING_DIM}"

    check("EMBEDDING_DIM is 512", _dim)

    # --- 4. process_frame ---------------------------------------------------
    print("\n[4] process_frame on a test image")
    image = make_test_image()
    result = None

    def _runs():
        nonlocal result
        result = pipeline.process_frame(image, "test-camera-id", "2026-08-22T14:03:11Z")
        return result is not None, f"returned {type(result).__name__}"

    check("process_frame(bytes, camera_id, ts) runs", _runs)

    def _has_detections():
        items = result if isinstance(result, list) else getattr(result, "detections", None)
        if items is None and isinstance(result, dict):
            items = result.get("detections")
        return items is not None, f"{len(items) if items is not None else 0} detection(s)"

    check("result exposes a detections list", _has_detections)

    items = result if isinstance(result, list) else getattr(result, "detections", None)
    if items is None and isinstance(result, dict):
        items = result.get("detections")
    items = items or []

    if items:
        first = items[0]

        def _field(name, aliases):
            def inner():
                for alias in aliases:
                    value = (
                        first.get(alias)
                        if isinstance(first, dict)
                        else getattr(first, alias, None)
                    )
                    if value is not None:
                        return True, f"found as `{alias}`"
                return False, f"none of {aliases} present"

            return inner

        print("\n[5] detection fields")
        check("vehicle_type", _field("vehicle_type", ["vehicle_type", "type", "label"]))
        check("bbox", _field("bbox", ["bbox", "box", "xyxy"]))
        check("veh_emb", _field("veh_emb", ["veh_emb", "embedding", "emb"]))

        print("\n[6] embedding is valid")

        def _get_emb():
            for alias in ("veh_emb", "embedding", "emb"):
                value = (
                    first.get(alias) if isinstance(first, dict) else getattr(first, alias, None)
                )
                if value is not None:
                    return list(value)
            return []

        def _dim_ok():
            emb = _get_emb()
            return len(emb) == 512, f"length={len(emb)}"

        check("exactly 512 numbers", _dim_ok)

        def _norm_ok():
            emb = _get_emb()
            if not emb:
                return False, "no embedding"
            norm = sum(v * v for v in emb) ** 0.5
            # THE most commonly missed requirement. Without normalization every
            # match score is wrong, and nothing anywhere reports an error.
            return abs(norm - 1.0) < 1e-3, f"L2 norm = {norm:.6f} (must be 1.0)"

        check("L2-normalized (length exactly 1.0)", _norm_ok)

        print("\n[7] bbox shape")

        def _bbox_ok():
            for alias in ("bbox", "box", "xyxy"):
                value = (
                    first.get(alias) if isinstance(first, dict) else getattr(first, alias, None)
                )
                if value is not None:
                    return len(list(value)) == 4, f"{list(value)}"
            return False, "no bbox"

        check("bbox is [x1, y1, x2, y2]", _bbox_ok)
    else:
        print("\n  (no detections on the synthetic image — that is fine, it is not")
        print("   a real street photo. Re-run against a real frame to check fields.)")

    # --- 8. is_reachable ----------------------------------------------------
    print("\n[8] is_reachable agrees with the backend")

    def _reach_far():
        # 2 km apart, 5 seconds later: impossible at 60 km/h.
        return pipeline.is_reachable(2000, 5) is False, "2 km in 5 s must be False"

    def _reach_ok():
        # 2 km apart, 5 minutes later: easy.
        return pipeline.is_reachable(2000, 300) is True, "2 km in 5 min must be True"

    check("2 km in 5 seconds -> False", _reach_far)
    check("2 km in 5 minutes -> True", _reach_ok)

    # --- summary ------------------------------------------------------------
    passed = sum(1 for _, ok, _ in results if ok)
    failed = len(results) - passed

    print("\n" + "=" * 42)
    print(f"  {passed} passed, {failed} failed")
    if failed:
        print("\n  Fix these before sending the folder:")
        for label, ok, note in results:
            if not ok:
                print(f"    - {label}  ({note})")
        return 1

    print("\n  All good — send the folder over.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
