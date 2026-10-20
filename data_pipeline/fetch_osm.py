"""Phase 1, module 1b: fetch Hyderabad restaurants from OpenStreetMap, once.

Sends exactly ONE Overpass request (after checking the server has a free slot) and
saves the response bytes unchanged to data/raw/, plus a .meta.json record of how
the snapshot was taken. Both files are then marked read-only.

Safety rules (CLAUDE.md, DECISIONS.md D-005):
  - boundary = OSM relation 7868535, selected by ID (area 3607868535), never by name
  - write-once: refuses to run if a raw snapshot already exists
  - no retries, no loops; a busy server means "try again later"
  - a response carrying an Overpass "remark" (e.g. timeout) is partial data and is NOT saved

Run from the project root:
    .venv\\Scripts\\python data_pipeline\\fetch_osm.py

Standard library only.
"""

import hashlib
import json
import os
import re
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
STATUS_URL = "https://overpass-api.de/api/status"
USER_AGENT = "Dawat-portfolio-demo/0.1 (educational project; one-time restaurant fetch)"

RELATION_ID = 7868535
AREA_ID = 3600000000 + RELATION_ID
QUERY = (
    "[out:json][timeout:120];\n"
    f"area({AREA_ID})->.a;\n"
    # Anchored exact match (D-007). The 2026-09-30 snapshot was fetched with the older,
    # unanchored regex, which let in 15 internet_cafe rows; its .meta.json records that query.
    'nwr["amenity"~"^(restaurant|fast_food|cafe)$"](area.a);\n'
    "out center tags;\n"
)

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
SNAPSHOT_GLOB = "overpass_hyderabad_*.json"


def free_slots() -> tuple[int, str]:
    request = urllib.request.Request(STATUS_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        text = response.read().decode("utf-8", errors="replace")
    match = re.search(r"(\d+) slots? available now", text)
    return (int(match.group(1)) if match else 0), text


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252

    existing = sorted(p.name for p in RAW_DIR.glob(SNAPSHOT_GLOB) if not p.name.endswith(".meta.json"))
    if existing:
        print(f"Refusing to fetch: raw snapshot already exists ({', '.join(existing)}). data/raw/ is write-once.")
        return 1

    slots, status_text = free_slots()
    if slots < 1:
        print("Overpass has no free slot right now; no request sent. Server status:\n" + status_text)
        return 2
    print(f"Overpass status: {slots} slot(s) free. Sending one request…")

    fetched_at = datetime.now(timezone.utc)
    body = urllib.parse.urlencode({"data": QUERY}).encode()
    request = urllib.request.Request(OVERPASS_URL, data=body, headers={"User-Agent": USER_AGENT})
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            raw_bytes = response.read()
    except (urllib.error.URLError, TimeoutError) as err:
        print(f"Request failed after {time.monotonic() - started:.0f}s ({err}). Not retried; nothing saved. Try again later.")
        return 2
    print(f"Response received in {time.monotonic() - started:.0f}s.")

    data = json.loads(raw_bytes)  # must be valid JSON before anything is saved
    if "remark" in data:
        print(f"Overpass returned a remark, so the data may be partial: {data['remark']!r}. Nothing saved.")
        return 3
    elements = data.get("elements", [])
    if not elements:
        print("Overpass returned zero elements; that can't be right for Hyderabad. Nothing saved.")
        return 3

    stem = f"overpass_hyderabad_{fetched_at:%Y-%m-%d}"
    data_path = RAW_DIR / f"{stem}.json"
    meta_path = RAW_DIR / f"{stem}.meta.json"

    meta = {
        "source": "OpenStreetMap via Overpass API (© OpenStreetMap contributors, ODbL)",
        "endpoint": OVERPASS_URL,
        "query": QUERY,
        "boundary": {"osm_relation": RELATION_ID, "overpass_area": AREA_ID, "decision": "DECISIONS.md D-005"},
        "fetched_at_utc": fetched_at.isoformat(timespec="seconds"),
        "osm_data_timestamp": data.get("osm3s", {}).get("timestamp_osm_base"),
        "element_count": len(elements),
        "bytes": len(raw_bytes),
        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "file": data_path.name,
    }

    # Write to temp names first, then rename, so a crash never leaves a half-written snapshot.
    for path, payload in ((data_path, raw_bytes), (meta_path, (json.dumps(meta, indent=2) + "\n").encode())):
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(payload)
        os.replace(tmp, path)
        os.chmod(path, stat.S_IREAD)  # read-only (on Windows this sets the read-only attribute)

    print(f"Saved {data_path.name} ({len(elements)} elements, {len(raw_bytes):,} bytes) and {meta_path.name}.")
    print(f"OSM data as of {meta['osm_data_timestamp']}. Both files marked read-only.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
