r"""Cache OpenStreetMap tiles for offline use.

The demo runs with no internet. Leaflet's default tile layer fetches from the
network on every pan and zoom, so without this the map is blank on stage — the
single most visible way the demo can fail.

Downloads a small area around the demo cameras into dashboard/public/tiles/,
which Leaflet then reads as plain static files.

    .\.venv\Scripts\python.exe -m scripts.download_tiles
    .\.venv\Scripts\python.exe -m scripts.download_tiles --lat 31.50 --lng 74.33

Volume is deliberately small (a few hundred tiles) and re-running skips what is
already on disk.

⚠️ **Tiles do NOT come from tile.openstreetmap.org.** OSM's usage policy forbids
bulk downloading and their servers enforce it by answering **HTTP 200 with an
"Access blocked" image** rather than an error. The first version of this script
trusted the status code and wrote 528 identical error images to disk; the map
then rendered a wall of "Access blocked" on stage-day hardware, and every count
based check said the cache was fine. Tiles now come from Carto's basemap CDN,
which serves this volume without an API key, and every download is verified.

Carto was tried next and is also unusable: it now stamps **"API KEY REQUIRED"**
diagonally across every tile when no key is present. Real map data underneath, but
unshowable. Tiles therefore come from the German OSM community server, which
serves the standard OSM style cleanly. Verified by *looking at* a downloaded tile,
which is the only check that catches a watermark.

Attribution is already rendered by Leaflet in both map components.
"""

import argparse
import hashlib
import math
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

TILE_URL = "https://tile.openstreetmap.de/{z}/{x}/{y}.png"

USER_AGENT = "Traffic_Trace/0.1 (hackathon project; offline demo cache)"

# A provider that refuses bulk downloads answers 200 with one placeholder image
# for every request, so every tile lands byte-identical. Real tiles of different
# ground never are. Checking this is the difference between finding out here and
# finding out on stage.
IDENTICAL_TILE_LIMIT = 8

TILE_DIR = Path(__file__).resolve().parents[2] / "dashboard" / "public" / "tiles"

# Zoom 13 shows the whole city area, 17 is close enough to see a junction.
MIN_ZOOM, MAX_ZOOM = 13, 17


def deg2tile(lat: float, lng: float, zoom: int) -> tuple[int, int]:
    lat_rad = math.radians(lat)
    n = 2.0**zoom
    x = int((lng + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lat", type=float, default=25.0110, help="centre latitude")
    parser.add_argument("--lng", type=float, default=67.0403, help="centre longitude")
    parser.add_argument("--radius-km", type=float, default=3.0)
    parser.add_argument("--min-zoom", type=int, default=MIN_ZOOM)
    parser.add_argument("--max-zoom", type=int, default=MAX_ZOOM)
    args = parser.parse_args()

    # Rough degree offsets. Good enough for a demo bounding box.
    d_lat = args.radius_km / 111.0
    d_lng = args.radius_km / (111.0 * math.cos(math.radians(args.lat)))
    north, south = args.lat + d_lat, args.lat - d_lat
    west, east = args.lng - d_lng, args.lng + d_lng

    jobs: list[tuple[int, int, int]] = []
    for zoom in range(args.min_zoom, args.max_zoom + 1):
        x1, y1 = deg2tile(north, west, zoom)
        x2, y2 = deg2tile(south, east, zoom)
        for x in range(min(x1, x2), max(x1, x2) + 1):
            for y in range(min(y1, y2), max(y1, y2) + 1):
                jobs.append((zoom, x, y))

    print(f"centre {args.lat:.4f}, {args.lng:.4f}  radius {args.radius_km} km")
    print(f"zoom {args.min_zoom}-{args.max_zoom} -> {len(jobs)} tiles")
    print(f"into {TILE_DIR}\n")

    if len(jobs) > 5000:
        print("refusing: that is too many tiles. Reduce --radius-km or --max-zoom.")
        return 1

    saved = skipped = failed = 0
    digests: list[str] = []

    for i, (z, x, y) in enumerate(jobs, 1):
        path = TILE_DIR / str(z) / str(x) / f"{y}.png"
        if path.exists() and path.stat().st_size > 0:
            skipped += 1
            continue

        path.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(
            TILE_URL.format(z=z, x=x, y=y), headers={"User-Agent": USER_AGENT}
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = response.read()

            if not payload.startswith(b"\x89PNG"):
                print(f"  z{z}/{x}/{y} is not a PNG ({len(payload)} bytes) - stopping.")
                print(f"  The provider is not serving tiles. First bytes: {payload[:40]!r}")
                return 1

            digests.append(hashlib.md5(payload).hexdigest())
            if len(digests) == IDENTICAL_TILE_LIMIT and len(set(digests)) == 1:
                print(f"\n  STOPPING: the first {IDENTICAL_TILE_LIMIT} tiles are byte-identical.")
                print("  That is a provider refusing bulk downloads and serving one")
                print("  placeholder image for every request - exactly what OSM does.")
                print("  Nothing usable was written. Try a different TILE_URL.")
                return 1

            path.write_bytes(payload)
            saved += 1
            # Be a polite client; no heavy parallel load.
            time.sleep(0.05)
        except urllib.error.URLError as exc:
            failed += 1
            print(f"  failed z{z}/{x}/{y}: {exc}")

        if i % 50 == 0:
            print(f"  {i}/{len(jobs)}  saved={saved} skipped={skipped} failed={failed}")

    # Verify what is on disk, not just what this run wrote - a previous run may
    # have poisoned the cache, and skipped tiles never pass through the check above.
    on_disk = list(TILE_DIR.rglob("*.png"))
    total_mb = sum(f.stat().st_size for f in on_disk) / 1024 / 1024
    all_digests = {hashlib.md5(f.read_bytes()).hexdigest() for f in on_disk}

    print(f"\nsaved={saved} skipped={skipped} failed={failed}")
    print(f"cache now {len(on_disk)} tiles, {total_mb:.1f} MB, {len(all_digests)} distinct images")

    if on_disk and len(all_digests) <= max(2, len(on_disk) // 50):
        print("\n  WARNING: nearly every cached tile is the same image. That is a")
        print("  blocked-provider placeholder, not a map. Delete the folder and")
        print("  re-run:  Remove-Item -Recurse -Force dashboard\\public\\tiles")
        return 1

    print("\nTurn WiFi off and reload the map to verify it still draws.")
    return 1 if failed and saved == 0 else 0


if __name__ == "__main__":
    sys.exit(main())
