"""Phase 1, module 4 (input): fetch the outline of OSM relation 7868535, once.

Used only to draw the city outline behind the map plot. Same rules as fetch_osm.py:
status check first, ONE request, no retries, write-once raw snapshot plus .meta.json,
both marked read-only.

Run from the project root:
    .venv\\Scripts\\python data_pipeline\\fetch_boundary.py
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

QUERY = f"[out:json][timeout:60];\nrel({RELATION_ID});\nout geom;\n"
STEM_PREFIX = f"osm_relation_{RELATION_ID}_"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    existing = sorted(p.name for p in RAW_DIR.glob(STEM_PREFIX + "*.json") if not p.name.endswith(".meta.json"))
    if existing:
        print(f"Refusing to fetch: boundary snapshot already exists ({', '.join(existing)}).")
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
    relations = [e for e in data.get("elements", []) if e.get("type") == "relation" and e.get("id") == RELATION_ID]
    outer_ways = [m for r in relations for m in r.get("members", []) if m.get("role") == "outer" and m.get("geometry")]
    if not outer_ways:
        print("No outer-way geometry in the response. Nothing saved.")
        return 3

    data_path = RAW_DIR / f"{STEM_PREFIX}{fetched_at:%Y-%m-%d}.json"
    meta_path = data_path.with_name(data_path.stem + ".meta.json")
    meta = {
        "source": "OpenStreetMap via Overpass API (© OpenStreetMap contributors, ODbL)",
        "purpose": "outline of the fetch boundary, for the map plot only",
        "endpoint": OVERPASS_URL,
        "query": QUERY,
        "fetched_at_utc": fetched_at.isoformat(timespec="seconds"),
        "osm_data_timestamp": data.get("osm3s", {}).get("timestamp_osm_base"),
        "outer_ways": len(outer_ways),
        "outer_points": sum(len(m["geometry"]) for m in outer_ways),
        "bytes": len(raw_bytes),
        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "file": data_path.name,
    }
    for path, payload in ((data_path, raw_bytes), (meta_path, (json.dumps(meta, indent=2) + "\n").encode())):
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(payload)
        os.replace(tmp, path)
        os.chmod(path, stat.S_IREAD)

    print(f"Saved {data_path.name} ({meta['outer_ways']} outer ways, {meta['outer_points']} points, "
          f"{len(raw_bytes):,} bytes) and {meta_path.name}. Both marked read-only.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
