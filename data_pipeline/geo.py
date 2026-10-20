"""Small geometry helpers for the data pipeline (standard library only)."""

import hashlib
import json
import math
import sys
from pathlib import Path

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def metres(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle (haversine) distance between two (lat, lon) points, in metres."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(h))


def load_verified(prefix: str) -> tuple[dict, dict]:
    """Load the single data/raw/<prefix>*.json snapshot after checking its sha256 against .meta.json."""
    files = sorted(p for p in RAW_DIR.glob(prefix + "*.json") if not p.name.endswith(".meta.json"))
    if len(files) != 1:
        sys.exit(f"Expected exactly one {prefix}*.json in data/raw/, found {len(files)}.")
    raw = files[0].read_bytes()
    meta = json.loads(files[0].with_name(files[0].stem + ".meta.json").read_bytes())
    if hashlib.sha256(raw).hexdigest() != meta["sha256"]:
        sys.exit(f"{files[0].name} does not match its .meta.json sha256.")
    return json.loads(raw), meta


def boundary_segments(boundary: dict) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """All (lon, lat) edge segments of the relation's outer and inner ways.

    Ray casting only needs every edge once; the ways do not have to be stitched into rings,
    and inner ways (holes) are handled by the same crossing parity."""
    segments = []
    for rel in (e for e in boundary["elements"] if e.get("type") == "relation"):
        for m in rel.get("members", []):
            if m.get("role") in ("outer", "inner") and m.get("geometry"):
                pts = [(p["lon"], p["lat"]) for p in m["geometry"]]
                segments.extend(zip(pts, pts[1:]))
    return segments


def point_in_boundary(lat: float, lon: float, segments) -> bool:
    """Ray casting: count how many edges a ray going east from the point crosses; odd = inside."""
    inside = False
    for (x1, y1), (x2, y2) in segments:
        if (y1 > lat) != (y2 > lat):
            x_cross = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if lon < x_cross:
                inside = not inside
    return inside
