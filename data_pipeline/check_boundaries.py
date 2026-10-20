"""Phase 1, module 1a: confirm the Hyderabad boundary before the real fetch.

History (see DECISIONS.md D-005): matching areas by name ("Hyderabad", administrative)
returned two Indian areas: relation 7255986 (Hyderabad District, admin_level 5) and
relation 7868535 (Hyderabad, admin_level 8). Saif checked 7868535 on openstreetmap.org:
it covers HITEC City, Gachibowli, Madhapur and Kondapur, and contains the district.
Decision: use relation 7868535 only, selected by ID.

This script confirms that choice with ONE Overpass request:
  - the relation's name tags, admin level and bounding box
  - for each landmark: is the point inside area 3607868535?
    (Overpass area id = 3600000000 + relation id)

Read-only; saves nothing. Exits 1 if any landmark lands on the wrong side.
Run from the project root:
    .venv\\Scripts\\python data_pipeline\\check_boundaries.py
"""

import json
import sys
import urllib.error
import urllib.parse
import urllib.request

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "Dawat-portfolio-demo/0.1 (educational project; boundary check)"

RELATION_ID = 7868535
AREA_ID = 3600000000 + RELATION_ID

# (label, lat, lon, expected_inside). Coordinates are approximate landmark centres.
LANDMARKS = [
    ("HITEC City", 17.4504, 78.3808, True),
    ("Madhapur", 17.4483, 78.3915, True),
    ("Gachibowli", 17.4401, 78.3489, True),
    ("Kondapur", 17.4699, 78.3578, True),
    ("Charminar (old city, control)", 17.3616, 78.4747, True),
    ("Hyderabad, Sindh, Pakistan (control)", 25.3960, 68.3578, False),
]
# Informational only (no expectation): Secunderabad Cantonment is governed separately from GHMC.
INFO_LANDMARKS = [("Secunderabad station", 17.4399, 78.4983)]


def build_query() -> str:
    parts = ["[out:json][timeout:60];", f"rel({RELATION_ID});out tags bb;"]
    for i, (_, lat, lon, *_) in enumerate(LANDMARKS + [(*x, None) for x in INFO_LANDMARKS]):
        # A marker element, then the area only if the point is inside it.
        parts.append(f'make marker idx="{i}";out;')
        parts.append(f"is_in({lat},{lon})->.a;area.a({AREA_ID});out ids;")
    return "".join(parts)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
    body = urllib.parse.urlencode({"data": build_query()}).encode()
    request = urllib.request.Request(OVERPASS_URL, data=body, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            elements = json.load(response)["elements"]
    except (urllib.error.URLError, TimeoutError) as err:
        print(f"Overpass unavailable ({err}). Nothing was retried; try again later.")
        return 2

    relation = next(e for e in elements if e["type"] == "relation")
    tags, b = relation["tags"], relation["bounds"]
    print(f"Relation {RELATION_ID}: name={tags.get('name')!r}, name:en={tags.get('name:en')!r}, "
          f"official_name={tags.get('official_name')!r}, admin_level={tags.get('admin_level')}")
    print(f"  bounding box: lat {b['minlat']:.3f}–{b['maxlat']:.3f}, lon {b['minlon']:.3f}–{b['maxlon']:.3f}\n")

    # Walk the markers: a marker followed by the area means "inside".
    inside: dict[int, bool] = {}
    current = None
    for el in elements:
        if el["type"] == "marker":
            current = int(el["tags"]["idx"])
            inside[current] = False
        elif el["type"] == "area" and current is not None:
            inside[current] = True

    failures = 0
    all_points = LANDMARKS + [(label, lat, lon, None) for label, lat, lon in INFO_LANDMARKS]
    for i, (label, lat, lon, expected) in enumerate(all_points):
        result = "INSIDE " if inside.get(i) else "outside"
        if expected is None:
            verdict = "(info)"
        elif inside.get(i) == expected:
            verdict = "✓ as expected"
        else:
            verdict = "✗ UNEXPECTED"
            failures += 1
        print(f"  {result}  {label:<38} ({lat}, {lon})  {verdict}")

    print(f"\n{'All expectations met.' if not failures else f'{failures} unexpected result(s).'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
