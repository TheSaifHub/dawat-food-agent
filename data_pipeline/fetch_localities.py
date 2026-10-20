"""Phase 2, module 2a (input): fetch named locality points inside OSM relation 7868535, once.

Saif's idea (docs/phase2_backlog.md): build localities.csv from OSM place points instead
of typing coordinates by hand. Fetches place=suburb / neighbourhood / quarter (quarter sits
between the two in OSM's hierarchy and costs nothing extra in the same request).

Same rules as fetch_osm.py: status check first, ONE request, no retries, write-once raw
snapshot plus .meta.json, both marked read-only.

Run from the project root:
    .venv\\Scripts\\python data_pipeline\\fetch_localities.py
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
from collections import Counter
from datetime import datetime, timezone

from fetch_osm import AREA_ID, OVERPASS_URL, RAW_DIR, RELATION_ID, USER_AGENT, free_slots

PLACE_TYPES = ("suburb", "neighbourhood", "quarter")
QUERY = (
    "[out:json][timeout:60];\n"
    f"area({AREA_ID})->.a;\n"
    f'nwr["place"~"^({"|".join(PLACE_TYPES)})$"](area.a);\n'
    "out center tags;\n"
)
STEM_PREFIX = f"osm_places_{RELATION_ID}_"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    existing = sorted(p.name for p in RAW_DIR.glob(STEM_PREFIX + "*.json") if not p.name.endswith(".meta.json"))
    if existing:
        print(f"Refusing to fetch: localities snapshot already exists ({', '.join(existing)}).")
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
    elements = data.get("elements", [])
    if not elements:
        print("Zero place elements returned; that can't be right. Nothing saved.")
        return 3

    data_path = RAW_DIR / f"{STEM_PREFIX}{fetched_at:%Y-%m-%d}.json"
    meta_path = data_path.with_name(data_path.stem + ".meta.json")
    by_place = Counter(e.get("tags", {}).get("place") for e in elements)
    meta = {
        "source": "OpenStreetMap via Overpass API (© OpenStreetMap contributors, ODbL)",
        "purpose": "named locality points for data/reference/localities.csv (Phase 2, module 2a)",
        "endpoint": OVERPASS_URL,
        "query": QUERY,
        "boundary": {"osm_relation": RELATION_ID, "overpass_area": AREA_ID, "decision": "DECISIONS.md D-005"},
        "fetched_at_utc": fetched_at.isoformat(timespec="seconds"),
        "osm_data_timestamp": data.get("osm3s", {}).get("timestamp_osm_base"),
        "element_count": len(elements),
        "by_place": dict(by_place.most_common()),
        "bytes": len(raw_bytes),
        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "file": data_path.name,
    }
    for path, payload in ((data_path, raw_bytes), (meta_path, (json.dumps(meta, indent=2) + "\n").encode())):
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(payload)
        os.replace(tmp, path)
        os.chmod(path, stat.S_IREAD)

    print(f"Saved {data_path.name} ({len(elements)} elements: {dict(by_place.most_common())}, "
          f"{len(raw_bytes):,} bytes) and {meta_path.name}. Both marked read-only.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
