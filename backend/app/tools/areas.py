"""resolve_area: turn what the user typed ("madhapoor", "KPHB", "మాదాపూర్") into one covered area, or say
clearly that we can't (D-023; docs/backlog.md "Out-of-coverage areas").

Order of checks (each one returns):
  1. empty / city-level words ("hyderabad", "hyd")      → needs_area: ask for a specific area
  2. names VERIFIED to be outside our boundary (D-009)  → outside_coverage (never fuzzy-matched to a neighbour)
  3. exact match on a name or alias (spaces ignored)    → ok
  4. score ≥ AUTO_MIN and ≥ MARGIN ahead of the next area    → ok, matched_by "fuzzy" (mention it to the user)
  5. score ≥ CONFIRM_MIN and ≥ MARGIN ahead of the next area → confirm_area: ASK "did you mean X?" first
  6. anything else                                           → unknown_area, with suggestions to ask about

Thresholds come from measured scores (rapidfuzz ratio on 26 typos and ~90 real local place names that are
not in our list, 2026-09-30):
  - 88+ : typos and spelling variants of OUR areas (gachibouli 90, ameerpt 93, secundrabad 96,
          upparpally→Upperpally 90, quthbullapur→Qutubullapur 92); no other place scored this high.
  - 80–87: BOTH real typos (madhapoor 82, jubli hills 82, kondapoor 82) AND different places
          (shamirpet→Shaikpet 82, serilingampally→Lingampally 85). Edit distance can't tell them apart, so
          the user decides.
  - MARGIN stops a pick between two close areas ("amerpet" is equally near Ameerpet and Amberpet).
A near-miss is never silently snapped to a covered area.
"""

from rapidfuzz import fuzz

from app.text import compact
from app.tools.reference import Reference

AUTO_MIN, CONFIRM_MIN, MARGIN, SUGGEST_MIN, MAX_SUGGESTIONS = 88, 80, 10, 70, 3
COVERAGE = "Hyderabad city (OpenStreetMap relation 7868535: the old city, Secunderabad and the western IT corridor)"
CITY_WORDS = {"hyderabad", "hyd", "hyderbad", "hydrabad", "secunderabadhyderabad", "city", "anywhere", "హైదరాబాద్"}
# Checked against the boundary polygon in Phase 2 (D-009); both lie just outside relation 7868535.
KNOWN_OUTSIDE = {
    "manikonda": "Manikonda: both OpenStreetMap points for it are outside our boundary (D-009)",
    "bowenpally": "Bowenpally: about 118 m outside our boundary, in the Secunderabad Cantonment notch (D-009)",
    "bowenpalli": "Bowenpally: about 118 m outside our boundary, in the Secunderabad Cantonment notch (D-009)",
}


def area_json(area: dict) -> dict:
    return {"area_id": area["area_id"], "name": area["name"]}


def resolve_area(ref: Reference, text: str | None) -> dict:
    q = compact(text or "")
    if not q or q in CITY_WORDS:
        return {"status": "needs_area", "input": text,
                "message": "Ask the user for a specific area or locality (e.g. Madhapur, Banjara Hills, Charminar)."}
    if q in KNOWN_OUTSIDE:
        return {"status": "outside_coverage", "input": text, "reason": KNOWN_OUTSIDE[q], "coverage": COVERAGE,
                "message": "Tell the user Dawat does not deliver there yet. Do not suggest restaurants there."}

    best: dict[str, float] = {}
    for area_id, key in ref.area_keys:
        if key == q:
            return {"status": "ok", "area": area_json(ref.areas[area_id]), "matched_by": "exact", "input": text}
        s = fuzz.ratio(q, key)
        if s > best.get(area_id, 0):
            best[area_id] = s
    ranked = sorted(best.items(), key=lambda kv: (-kv[1], kv[0]))
    top_id, top = ranked[0] if ranked else (None, 0)
    runner_up = ranked[1][1] if len(ranked) > 1 else 0
    clear_lead = top - runner_up >= MARGIN
    if top >= AUTO_MIN and clear_lead:
        return {"status": "ok", "area": area_json(ref.areas[top_id]), "matched_by": "fuzzy", "input": text,
                "message": f"Interpreted '{text}' as {ref.areas[top_id]['name']}; mention this to the user."}
    if top >= CONFIRM_MIN and clear_lead:
        return {"status": "confirm_area", "input": text, "candidate": area_json(ref.areas[top_id]), "coverage": COVERAGE,
                "message": f"Ask the user: did you mean {ref.areas[top_id]['name']}? Continue with it only if they say "
                           "yes; if not, their area may be outside our coverage, so say so clearly."}
    suggestions = [area_json(ref.areas[a]) for a, s in ranked[:MAX_SUGGESTIONS] if s >= SUGGEST_MIN]
    return {"status": "unknown_area", "input": text, "suggestions": suggestions, "coverage": COVERAGE,
            "message": ("Ask the user whether they meant one of the suggestions. " if suggestions else "") +
                       "If their area is outside our coverage, say so clearly; never assume a nearby area."}
