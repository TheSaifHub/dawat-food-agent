"""Phase 2, module 2a: one request to look for well-known area names missing from the locality points.

Searches ANY place=* tag (town, city, village, locality, …) for these names in a box around
the city, not only inside the boundary, so "outside relation 7868535" can be told apart from
"not in OSM at all". Inside/outside is decided locally against the boundary outline
(point_in_boundary below, tested on known points before use).

Same fetch rules as fetch_osm.py: status check, ONE request, no retries, write-once
read-only snapshot plus .meta.json.

Run from the project root:
    .venv\\Scripts\\python data_pipeline\\check_missing_areas.py
"""

import hashlib
import json
import os
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from fetch_osm import OVERPASS_URL, RAW_DIR, RELATION_ID, USER_AGENT, free_slots

# Name patterns (case-insensitive; tolerate spacing variants).
NAMES_REGEX = "secunderabad|amber ?pet|tarnaka|malkaj ?giri|bowen ?pall|ecil|e\\\\.c\\\\.i\\\\.l|manikonda"
SEARCH_BOX = (17.20, 78.15, 17.65, 78.70)  # south, west, north, east: a little wider than the boundary
QUERY = (
    "[out:json][timeout:60];\n"
    f'nwr["place"]["name"~"{NAMES_REGEX}",i]({",".join(map(str, SEARCH_BOX))});\n'
    "out center tags;\n"
)
STEM_PREFIX = f"osm_missing_area_check_{RELATION_ID}_"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    existing = sorted(p.name for p in RAW_DIR.glob(STEM_PREFIX + "*.json") if not p.name.endswith(".meta.json"))
    if existing:
        print(f"Refusing to fetch: snapshot already exists ({', '.join(existing)}).")
        return 1
    slots, status_text = free_slots()
    if slots < 1:
        print("Overpass has no free slot right now; no request sent. Server status:\n" + status_text)
        return 2
    print(f"Overpass status: {slots} slot(s) free. Sending one request…")

    fetched_at = datetime.now(timezone.utc)
    request = urllib.request.Request(OVERPASS_URL, data=urllib.parse.urlencode({"data": QUERY}).encode(),
                                     headers={"User-Agent": USER_AGENT})
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw_bytes = response.read()
    except (urllib.error.URLError, TimeoutError) as err:
        print(f"Request failed after {time.monotonic() - started:.0f}s ({err}). Not retried; nothing saved.")
        return 2
    print(f"Response received in {time.monotonic() - started:.0f}s.")

    data = json.loads(raw_bytes)
    if "remark" in data:
        print(f"Overpass returned a remark (possibly partial): {data['remark']!r}. Nothing saved.")
        return 3
    elements = data.get("elements", [])  # zero results is a valid answer here ("none exist")

    data_path = RAW_DIR / f"{STEM_PREFIX}{fetched_at:%Y-%m-%d}.json"
    meta_path = data_path.with_name(data_path.stem + ".meta.json")
    meta = {
        "source": "OpenStreetMap via Overpass API (© OpenStreetMap contributors, ODbL)",
        "purpose": "check whether 7 well-known area names exist under any place=* tag (module 2a)",
        "endpoint": OVERPASS_URL, "query": QUERY,
        "fetched_at_utc": fetched_at.isoformat(timespec="seconds"),
        "osm_data_timestamp": data.get("osm3s", {}).get("timestamp_osm_base"),
        "element_count": len(elements), "bytes": len(raw_bytes),
        "sha256": hashlib.sha256(raw_bytes).hexdigest(), "file": data_path.name,
    }
    for path, payload in ((data_path, raw_bytes), (meta_path, (json.dumps(meta, indent=2) + "\n").encode())):
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(payload)
        os.replace(tmp, path)
        os.chmod(path, stat.S_IREAD)

    print(f"Saved {data_path.name} ({len(elements)} elements) and {meta_path.name}. Both marked read-only.")
    for e in elements:
        t = e.get("tags", {})
        lat = e.get("lat", e.get("center", {}).get("lat"))
        lon = e.get("lon", e.get("center", {}).get("lon"))
        print(f"  {e['type']}/{e['id']}  place={t.get('place')!s:<14} name={t.get('name')!r}  ({lat}, {lon})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
