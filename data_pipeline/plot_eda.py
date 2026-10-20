"""Phase 1, module 4: EDA charts → results/eda/*.png

Charts read their numbers from results/eda/stats.json and chains.json (modules 2–3),
so every chart matches the numbers the insights doc will cite. The map reads point
coordinates from the verified raw snapshot and the city outline from the boundary snapshot.

Colours follow the dataviz reference palette (light mode):
  restaurant = slot 1 blue, fast_food = slot 2 orange, cafe = slot 3 aqua.
Slots 1–3 are the set validated for all-pairs use (scatter/map). The same entity always
gets the same colour across charts. Single-series bars use slot 1.

Validation record (2026-09-30, dataviz skill scripts/validate_palette.js
"#2a78d6,#eb6834,#1baf7a" --mode light --pairs all --surface "#fcfcfb"):
  PASS lightness band, chroma floor, CVD separation (worst ΔE 9.2 deutan, cafe↔fast_food),
  normal-vision floor (worst ΔE 24.0); WARN contrast: #1baf7a is 2.74:1 on the surface,
  so the relief rule applies: types are always named in text (legend with counts, bar labels).

Run from the project root:
    .venv\\Scripts\\python data_pipeline\\plot_eda.py
"""

import hashlib
import json
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # file output only, no window
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
EDA_DIR = ROOT / "results" / "eda"

# ─── palette & chrome (dataviz references/palette.md, light) ────────────
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
TYPE_COLOURS = {"restaurant": "#2a78d6", "fast_food": "#eb6834", "cafe": "#1baf7a"}
TYPE_LABELS = {"restaurant": "Restaurant", "fast_food": "Fast food", "cafe": "Café"}
SINGLE = TYPE_COLOURS["restaurant"]
ATTRIBUTION = "Data © OpenStreetMap contributors (ODbL). Snapshot {date}."

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": AXIS, "axes.labelcolor": INK_2, "xtick.color": MUTED, "ytick.color": INK_2,
    "text.color": INK, "font.family": "sans-serif", "font.size": 10,
    "axes.spines.top": False, "axes.spines.right": False,
})


# ─── inputs ────────────────────────────────────────────────────────────
def verified_snapshot(prefix: str) -> tuple[dict, dict]:
    files = sorted(p for p in RAW_DIR.glob(prefix + "*.json") if not p.name.endswith(".meta.json"))
    if len(files) != 1:
        sys.exit(f"Expected exactly one {prefix}*.json in data/raw/, found {len(files)}.")
    raw = files[0].read_bytes()
    meta = json.loads(files[0].with_name(files[0].stem + ".meta.json").read_bytes())
    if hashlib.sha256(raw).hexdigest() != meta["sha256"]:
        sys.exit(f"{files[0].name} does not match its .meta.json sha256.")
    return json.loads(raw), meta


def load_json(name: str) -> dict:
    return json.loads((EDA_DIR / name).read_text(encoding="utf-8"))


# ─── helpers ───────────────────────────────────────────────────────────
def finish(fig, ax, title: str, subtitle: str, note: str, filename: str) -> Path:
    ax.set_title(title, loc="left", fontsize=13, fontweight="bold", color=INK, pad=22)
    ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=9.5, color=INK_2, va="bottom")
    fig.text(0.01, 0.01, note, fontsize=7.5, color=MUTED, ha="left", va="bottom")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    path = EDA_DIR / filename
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def hbar(items: list[tuple[str, float]], colours, title, subtitle, note, filename, value_fmt="{:,.0f}", xmax=None):
    """Horizontal bars, largest on top, value labelled at each bar end (ink, not series colour)."""
    labels = [k for k, _ in items][::-1]
    values = [v for _, v in items][::-1]
    colours = colours[::-1] if isinstance(colours, list) else [colours] * len(values)
    fig, ax = plt.subplots(figsize=(8, 0.34 * len(items) + 1.4))
    ax.barh(labels, values, height=0.72, color=colours)  # gap between bars = surface
    top = xmax or max(values) * 1.12
    ax.set_xlim(0, top)
    for y, v in enumerate(values):
        ax.text(v + top * 0.01, y, value_fmt.format(v), va="center", fontsize=8.5, color=INK_2)
    ax.xaxis.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    return finish(fig, ax, title, subtitle, note, filename)


# ─── charts ────────────────────────────────────────────────────────────
def chart_map(places: dict, boundary: dict, note: str) -> Path:
    fig, ax = plt.subplots(figsize=(9, 7.2))
    rel = next(e for e in boundary["elements"] if e.get("type") == "relation")
    for member in rel["members"]:
        if member.get("role") == "outer" and member.get("geometry"):
            xs = [pt["lon"] for pt in member["geometry"]]
            ys = [pt["lat"] for pt in member["geometry"]]
            ax.plot(xs, ys, color=INK_2, linewidth=1.2, zorder=1)

    counts = {}
    for amenity in ("restaurant", "fast_food", "cafe"):  # biggest group drawn first, smaller on top
        pts = [(e.get("lon", e.get("center", {}).get("lon")), e.get("lat", e.get("center", {}).get("lat")))
               for e in places["elements"] if e.get("tags", {}).get("amenity") == amenity]
        counts[amenity] = len(pts)
        ax.scatter([p[0] for p in pts], [p[1] for p in pts], s=14, color=TYPE_COLOURS[amenity],
                   edgecolors=SURFACE, linewidths=0.4, alpha=0.9, zorder=2,
                   label=f"{TYPE_LABELS[amenity]} ({counts[amenity]:,})")

    mid_lat = sum(ax.get_ylim()) / 2
    ax.set_aspect(1 / math.cos(math.radians(mid_lat)))  # so 1 km looks the same both ways
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.grid(True, color=GRID, linewidth=0.5)
    ax.set_axisbelow(True)
    # Lower-left corner is outside the boundary, so the legend hides no points or outline.
    legend = ax.legend(loc="lower left", frameon=True, fontsize=9, title="Type", title_fontsize=9, markerscale=1.6)
    legend.get_frame().set(edgecolor=AXIS, facecolor=SURFACE)
    total = sum(counts.values())
    return finish(fig, ax, "Where the food places are",
                  f"{total:,} food places inside OSM relation 7868535 (grey outline), coloured by type",
                  note, "map_places_by_type.png")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    EDA_DIR.mkdir(parents=True, exist_ok=True)
    places, pmeta = verified_snapshot("overpass_hyderabad_")
    boundary, _ = verified_snapshot("osm_relation_7868535_")
    stats, chains = load_json("stats.json"), load_json("chains.json")
    note = ATTRIBUTION.format(date=pmeta["osm_data_timestamp"][:10])
    written = []

    # 1. Map
    written.append(chart_map(places, boundary, note))

    # 2. Places by type
    by_type = stats["population"]["food_by_amenity"]
    order = sorted(by_type, key=by_type.get, reverse=True)
    written.append(hbar([(TYPE_LABELS[a], by_type[a]) for a in order], [TYPE_COLOURS[a] for a in order],
                        "Food places by type", f"{stats['population']['food_places']:,} food places "
                        f"(15 internet cafés excluded, D-007)", note, "places_by_type.png"))

    # 3. Tag coverage
    cov = stats["coverage_of_food_places"]
    keys = [("name", "Name"), ("cuisine", "Cuisine"), ("any_addr_tag", "Any address tag"),
            ("addr:street", "Street"), ("addr:postcode", "Postcode"), ("opening_hours", "Opening hours"),
            ("brand", "Brand"), ("name:te", "Telugu name"), ("any_area_tag", "Any area tag"),
            ("addr:suburb", "Suburb")]
    items = sorted(((label, cov[k]["pct"]) for k, label in keys), key=lambda kv: kv[1], reverse=True)
    written.append(hbar(items, SINGLE, "How complete are the OSM tags?",
                        "Share of food places that have each tag (%)", note, "tag_coverage.png",
                        value_fmt="{:.1f}%", xmax=110))

    # 4. Top cuisines
    top_cuisines = [(c["cuisine"].replace("_", " "), c["places"]) for c in stats["cuisine"]["top"]]
    written.append(hbar(top_cuisines, SINGLE, "Most common cuisine tags",
                        f"Top {len(top_cuisines)} values; only {cov['cuisine']['pct']}% of places have a cuisine tag",
                        note, "top_cuisines.png"))

    # 5. Top chains (display = most common spelling that isn't all lower case)
    def display_name(chain: dict) -> str:
        names = [v["name"] for v in chain["name_variants"]]
        return next((n for n in names if n != n.lower()), names[0].title())

    top = chains["top_chains"][:15]
    written.append(hbar([(display_name(c), c["places"]) for c in top], SINGLE,
                        "Largest chains (by shared core name)",
                        "Places per chain, counting only, before any Phase 2 review or merge", note,
                        "top_chains.png"))

    for path in written:
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
