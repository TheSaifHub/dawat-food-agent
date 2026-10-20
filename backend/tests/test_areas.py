"""resolve_area (D-023): exact and typo matches resolve; areas outside coverage and names we don't know are
never snapped to a nearby covered area. Runs on the real area list (rolled-back database connection)."""

import pytest

from app.text import compact
from app.tools.areas import KNOWN_OUTSIDE, resolve_area
from app.tools.reference import Reference, get_reference


@pytest.fixture
def ref(db) -> Reference:
    return get_reference(db)


@pytest.mark.parametrize("text, area_id", [
    ("Madhapur", "madhapur"), ("  MADHAPUR ", "madhapur"), ("Banjara Hills", "banjara-hills"),
    ("banjarahills", "banjara-hills"), ("KPHB", "kphb-colony"), ("hitech city", "hitec-city"), ("HITEC City", "hitec-city"),
    ("Kachiguda", "kacheguda"), ("LB Nagar", "lb-nagar"), ("Secunderabad", "secunderabad"),
])
def test_exact_names_and_aliases(ref, text, area_id):
    r = resolve_area(ref, text)
    assert (r["status"], r["area"]["area_id"], r["matched_by"]) == ("ok", area_id, "exact")


@pytest.mark.parametrize("text, area_id", [
    ("gachibouli", "gachibowli"), ("kukatpalli", "kukatpally"), ("secundrabad", "secunderabad"), ("ameerpt", "ameerpet"),
    ("amberpt", "amberpet"), ("sr nagr", "sr-nagar"), ("mehdipatanam", "mehdipatnam"), ("dilsuknagar", "dilsukh-nagar"),
    # spelling variants of the same place
    ("upparpally", "upperpally"), ("quthbullapur", "qutubullapur"), ("bharat nagar", "bharath-nagar"),
])
def test_close_typos_resolve_and_say_so(ref, text, area_id):
    r = resolve_area(ref, text)
    assert (r["status"], r["area"]["area_id"], r["matched_by"]) == ("ok", area_id, "fuzzy")
    assert "mention this to the user" in r["message"]


@pytest.mark.parametrize("text, area_id", [("madhapoor", "madhapur"), ("jubli hills", "jubilee-hills"),
                                           ("kondapoor", "kondapur")])
def test_looser_typos_are_confirmed_with_the_user_first(ref, text, area_id):
    r = resolve_area(ref, text)
    assert (r["status"], r["candidate"]["area_id"]) == ("confirm_area", area_id)
    assert "area" not in r


@pytest.mark.parametrize("text, lookalike", [("shamirpet", "shaikpet"), ("serilingampally", "lingampally")])
def test_different_places_that_look_like_our_areas_are_never_resolved(ref, text, lookalike):
    """Shamirpet (a town north of the city) is 82 from Shaikpet; Serilingampally (a whole zone) is 85 from
    Lingampally. Edit distance can't tell them from typos, so the user must be asked."""
    r = resolve_area(ref, text)
    assert r["status"] == "confirm_area" and r["candidate"]["area_id"] == lookalike and "area" not in r


@pytest.mark.parametrize("text", ["Manikonda", "manikonda", "Bowenpally", "bowenpalli", "BOWEN PALLY"])
def test_verified_outside_areas_are_refused_clearly(ref, text):
    r = resolve_area(ref, text)
    assert r["status"] == "outside_coverage"
    assert "area" not in r and "suggestions" not in r


@pytest.mark.parametrize("text", ["shamshabad", "kompally", "medchal", "kokapet", "narsingi", "nizampet", "bachupally",
                                  "ghatkesar", "gandipet", "puppalaguda", "old city", "Mumbai", "zzzz",
                                  # real places scoring 74–77 against one of ours with a clear lead (probe, 2026-09-30)
                                  "boduppal", "pocharam", "chintal", "mallampet"])
def test_unknown_names_are_never_snapped_to_a_covered_area(ref, text):
    r = resolve_area(ref, text)
    assert r["status"] == "unknown_area"
    assert "area" not in r
    assert "never assume a nearby area" in r["message"]


def test_a_typo_between_two_areas_is_asked_not_guessed(ref):
    """"amerpet" is one letter from both Ameerpet and Amberpet (equal scores): it must not pick one."""
    r = resolve_area(ref, "amerpet")
    assert r["status"] == "unknown_area"
    assert {s["area_id"] for s in r["suggestions"]} >= {"ameerpet", "amberpet"}


def test_near_miss_offers_suggestions_to_ask_about(ref):
    r = resolve_area(ref, "kompally")
    assert [s["area_id"] for s in r["suggestions"]] == ["nampally"]


@pytest.mark.parametrize("text", [None, "", "   ", "Hyderabad", "hyd", "HYDERABAD"])
def test_city_level_input_asks_for_an_area(ref, text):
    assert resolve_area(ref, text)["status"] == "needs_area"


def test_every_stored_name_and_alias_resolves_to_its_own_area(db, ref):
    """No alias is shadowed by another area once spaces are ignored, and none resolves by fuzzy luck."""
    rows = db.execute("select area_id, alias from public.area_aliases union select area_id, name from public.areas").fetchall()
    wrong = [(r["alias"], r["area_id"], res.get("area", {}).get("area_id"))
             for r in rows if (res := resolve_area(ref, r["alias"]))["status"] != "ok"
             or res["area"]["area_id"] != r["area_id"] or res["matched_by"] != "exact"]
    assert len(rows) > 300 and wrong == []


def test_telugu_area_names_resolve(db, ref):
    rows = db.execute("select area_id, name_te from public.areas where name_te is not null").fetchall()
    assert rows, "expected some Telugu area names from OSM"
    assert all(resolve_area(ref, r["name_te"]).get("area", {}).get("area_id") == r["area_id"] for r in rows)


def test_known_outside_names_are_not_in_the_area_list(ref):
    keys = {k for _, k in ref.area_keys}
    assert not any(compact(name) in keys for name in KNOWN_OUTSIDE)
