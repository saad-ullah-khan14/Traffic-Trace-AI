"""
Phase 16 — replay.py

Simulates N phone cameras by replaying a folder of recorded frames against
Muhammad's ingest API, preserving original timestamps and playback speed.
This is also the fallback demo tool if live phones fail on stage.

Usage:
    python tools/replay.py --folder recordings/ --cameras cam-A,cam-B,cam-C --speed 1.0
    python tools/replay.py --folder recordings/ --cameras cam-A --speed 5.0 --dry-run

Expected folder layout:
    recordings/
        cam-A/
            manifest.json   <- [{"file": "frame_001.jpg", "ts": "2026-08-22T14:00:00Z"}, ...]
            frame_001.jpg
            frame_002.jpg
            ...
        cam-B/
            manifest.json
            ...

Expected tokens file (default: tools/tokens.json, override with --tokens):
    {
        "cam-A": "secret-token-for-cam-a",
        "cam-B": "secret-token-for-cam-b"
    }

Camera token is sent as a HEADER (per Muhammad's README, NOT a form field):
    -H "X-Camera-Token: <secret>"
"""

import argparse
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone

import requests


def _parse_ts(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def load_manifest(camera_dir):
    manifest_path = os.path.join(camera_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        raise FileNotFoundError(f"No manifest.json found in {camera_dir}")
    with open(manifest_path, "r") as f:
        entries = json.load(f)
    # Sort by timestamp so playback order is always correct, regardless of
    # how the manifest was written.
    entries.sort(key=lambda e: _parse_ts(e["ts"]))
    return entries


def load_tokens(tokens_path):
    if not os.path.exists(tokens_path):
        print(f"WARNING: tokens file not found at {tokens_path} — "
              f"requests will be sent without X-Camera-Token headers.")
        return {}
    # utf-8-sig, not utf-8: a tokens file written by PowerShell carries a BOM,
    # and json.load treats it as a syntax error. This is the demo's fallback
    # path - it does not get to be fussy about who wrote its input.
    with open(tokens_path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def send_frame(api_url, token, camera_id, frame_path, ts, dry_run):
    headers = {}
    if token:
        headers["X-Camera-Token"] = token

    if dry_run:
        print(f"  [DRY RUN] would POST {frame_path} (camera={camera_id}, ts={ts})")
        return True

    try:
        with open(frame_path, "rb") as f:
            files = {"frame": f}
            data = {"ts": ts}
            response = requests.post(api_url, headers=headers, files=files, data=data, timeout=10)
        # /api/frames answers 202 Accepted (queued, not yet processed), not 200.
        if response.status_code in (200, 202):
            print(f"  OK   {os.path.basename(frame_path)} (camera={camera_id}, ts={ts})")
            return True
        else:
            print(f"  FAIL {os.path.basename(frame_path)} — HTTP {response.status_code}: {response.text[:200]}")
            return False
    except requests.exceptions.RequestException as exc:
        print(f"  FAIL {os.path.basename(frame_path)} — {type(exc).__name__}: {exc}")
        return False


def replay_camera(camera_id, camera_dir, api_url, token, speed, dry_run, stats):
    entries = load_manifest(camera_dir)
    if not entries:
        print(f"[{camera_id}] manifest is empty, nothing to replay.")
        return

    print(f"[{camera_id}] starting replay: {len(entries)} frames, speed={speed}x")

    prev_ts = None
    for entry in entries:
        ts = entry["ts"]
        frame_path = os.path.join(camera_dir, entry["file"])

        if not os.path.exists(frame_path):
            print(f"[{camera_id}] SKIPPING missing file: {frame_path}")
            stats["failed"] += 1
            continue

        # Sleep to preserve the original inter-frame timing, scaled by --speed.
        if prev_ts is not None:
            real_gap = (_parse_ts(ts) - _parse_ts(prev_ts)).total_seconds()
            sleep_time = max(0.0, real_gap / speed)
            if sleep_time > 0:
                time.sleep(sleep_time)
        prev_ts = ts

        ok = send_frame(api_url, token, camera_id, frame_path, ts, dry_run)
        stats["sent" if ok else "failed"] += 1

    print(f"[{camera_id}] replay finished.")


def main():
    parser = argparse.ArgumentParser(description="Replay recorded frames against the ingest API.")
    parser.add_argument("--folder", required=True, help="Path to the recordings folder (contains per-camera subfolders).")
    parser.add_argument("--cameras", required=True, help="Comma-separated camera IDs to replay, e.g. cam-A,cam-B,cam-C")
    parser.add_argument("--speed", type=float, default=1.0, help="Playback speed multiplier (default 1.0 = real-time).")
    parser.add_argument("--api-url", default="http://localhost:8000/api/frames", help="Ingest API endpoint.")
    parser.add_argument("--tokens", default="tools/tokens.json", help="Path to the camera-token JSON file.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be sent, without making real HTTP requests.")

    args = parser.parse_args()

    camera_ids = [c.strip() for c in args.cameras.split(",") if c.strip()]
    if not camera_ids:
        print("ERROR: no camera IDs given via --cameras")
        sys.exit(1)

    tokens = load_tokens(args.tokens)

    stats = {"sent": 0, "failed": 0}
    threads = []

    for camera_id in camera_ids:
        camera_dir = os.path.join(args.folder, camera_id)
        if not os.path.isdir(camera_dir):
            print(f"ERROR: no folder found for camera '{camera_id}' at {camera_dir}")
            continue

        token = tokens.get(camera_id)
        t = threading.Thread(
            target=replay_camera,
            args=(camera_id, camera_dir, args.api_url, token, args.speed, args.dry_run, stats),
        )
        threads.append(t)

    print(f"\nStarting replay across {len(threads)} camera(s), speed={args.speed}x, "
          f"dry_run={args.dry_run}\n")

    start = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.time() - start

    print(f"\n{'=' * 50}")
    print(f"Replay complete in {elapsed:.1f}s")
    print(f"  Sent:   {stats['sent']}")
    print(f"  Failed: {stats['failed']}")


if __name__ == "__main__":
    main()
