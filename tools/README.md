# tools/ — Teammate 1

`replay.py` — feeds recorded street frames at `POST /api/frames` as if they came from a
live phone camera. This is the demo's fallback path: if the phones fail on stage, the
same pipeline runs against a recording and nothing else changes. The endpoint cannot
tell the difference — a camera is identified by the `X-Camera-Token` header and nothing
else.

```powershell
.\api\.venv\Scripts\python.exe tools\replay.py --folder tools\recordings --cameras cam-A,cam-B,cam-C --api-url http://<laptop-ip>:8000/api/frames
```

| Flag | Meaning |
|---|---|
| `--folder` | Holds one subfolder per camera |
| `--cameras` | Comma-separated subfolder names, which are also the `tokens.json` keys |
| `--speed` | Playback multiplier. `1.0` is real time |
| `--api-url` | Defaults to `http://localhost:8000/api/frames` |
| `--tokens` | Defaults to `tools/tokens.json` |
| `--dry-run` | Print what would be sent, post nothing |

Each camera folder needs a `manifest.json` listing its frames and capture times:

```json
[
    {"file": "frame_001.jpg", "ts": "2026-08-22T14:00:00Z"},
    {"file": "frame_002.jpg", "ts": "2026-08-22T14:00:02Z"}
]
```

The gaps between those timestamps are what the replay sleeps for, so a recording plays
back at the pace it was captured. One thread per camera, so three cameras replay
concurrently exactly as three phones would.

`tokens.json` maps each folder name to that camera's secret and is written by
`api/scripts/seed_cameras.py`. It is **gitignored** — those are live credentials.

`test_recordings/cam-A/` holds 3 sample frames, enough to prove the command works
before you need it. Verified end to end on 29 Aug 2026.
