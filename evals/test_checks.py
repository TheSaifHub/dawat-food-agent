"""The eval checks must FAIL on bad replies (CLAUDE.md: an eval that can't fail proves nothing). Pure, no models."""

from checks import check_turn, diet_notes_copied, expectations, names_spelled, numbers_grounded, script_of

RESULTS = [{"status": "ok", "results": [
    {"name": "Chicken Dum Biryani", "price": 240, "restaurant": {"name": "Annapurna"}},
    {"name": "Chicken Dum Biryani", "price": 270, "restaurant": {"name": "Hideout"}}]}]
PLAN = {"status": "ok", "plans": [{"restaurants": [{"restaurant": "Annapurna"}], "grand_total": 419,
                                   "diet_note": "2 main portions for 2; spicy (spice 2–3) for everyone, as asked."}]}


def test_an_invented_price_is_caught_even_without_a_rupee_sign():
    assert numbers_grounded("Annapurna: ₹240, Hideout: ₹270", RESULTS, [])["ok"]
    assert not numbers_grounded("Annapurna: ₹240, Hideout: ₹250", RESULTS, [])["ok"]
    assert not numbers_grounded("| Hideout | 255 |", RESULTS, [])["ok"]                  # a table cell, no ₹
    assert numbers_grounded("Under 300 as you asked: Hideout ₹270", RESULTS, ["biryani under 300"])["ok"]
    assert numbers_grounded("Top 5 options", RESULTS, [])["ok"]                          # small counts are fine


def test_a_misspelled_restaurant_is_caught():
    assert names_spelled("Try Annapurna for ₹240.", RESULTS)["ok"]
    bad = names_spelled("Try Annapura for ₹240.", RESULTS)
    assert not bad["ok"] and "Annapura" in bad["detail"].title()
    assert names_spelled("Biryani is great here.", RESULTS)["ok"]                         # not mentioned at all


def test_diet_notes_must_be_copied():
    assert diet_notes_copied("Best match ₹419\n2 main portions for 2; spicy (spice 2–3) for everyone, as asked.",
                             [PLAN])["ok"]
    assert not diet_notes_copied("Best match ₹419, all spicy!", [PLAN])["ok"]
    assert diet_notes_copied("anything", [{"status": "over_budget"}]) is None


def test_language_and_script_expectations_fail_when_wrong():
    assert script_of("మాధాపూర్ లో") == "telugu" and script_of("हाँ भाई") == "devanagari" and script_of("hi") == "latin"
    fails = {c["check"] for c in expectations({"script": "latin", "english": True}, "Haan bhai, yeh lo", [], 0)
             if not c["ok"]}
    assert fails == {"english_only"}
    assert not expectations({"script": "latin"}, "हाँ भाई", [], 0)[0]["ok"]


def test_tool_expectations_fail_when_wrong():
    calls = [{"tool": "search_restaurants", "arguments": {"query": "Paradise"}, "status": "needs_choice"},
             {"tool": "get_menu", "arguments": {"branch_id": "b-n1"}, "status": "ok"}]
    got = {c["check"]: c["ok"] for c in expectations(
        {"tools": ["search_restaurants", "plan_meal"], "no_tools": ["get_menu"], "args": {"search_restaurants": {"query": "Mehfil"}},
         "statuses": {"search_restaurants": "needs_choice"}, "orders": 0, "no_numbers": True, "reply_has_any": ["branch"]},
        "Which branch? Ameerpet has 12 options", calls, 1)}
    assert got == {"called search_restaurants": True, "called plan_meal": False, "did not call get_menu": False,
                   "search_restaurants arguments": False, "search_restaurants status needs_choice": True,
                   "reply mentions": True, "no prices yet": True, "orders placed = 0": False}


def test_a_failure_reply_fails_the_turn():
    checks = check_turn(reply="Dawat AI is busy right now.", status="busy", calls=[], tool_results_so_far=[],
                        this_turn_results=[], user_words=["hi"], expect={}, orders_placed=0)
    assert {c["check"]: c["ok"] for c in checks}["no_failure_reply"] is False


def test_reply_has_none_and_min_calls_fail_when_wrong():
    calls = [{"tool": "search_dishes", "arguments": {}, "status": "ok"}]
    got = {c["check"]: c["ok"] for c in expectations({"reply_has_none": ["₹99"], "min_calls": {"search_dishes": 2}},
                                                      "Added at ₹99!", calls, 0)}
    assert got == {"reply avoids": False, "search_dishes called ≥ 2×": False}


def test_result_keys_and_cart_nonveg_fail_when_wrong():
    calls = [{"tool": "plan_meal", "arguments": {}, "status": "ok"}]
    got = {c["check"]: c["ok"] for c in expectations(
        {"result_keys": {"plan_meal": ["preferences_applied"]}, "cart_nonveg": 0}, "ok", calls, 0,
        results=[{"status": "ok", "plans": []}], cart_nonveg=1)}
    assert got == {"plan_meal result has ['preferences_applied']": False, "non-veg items in cart = 0": False}
    good = expectations({"result_keys": {"plan_meal": ["preferences_applied"]}, "cart_nonveg": 0}, "ok", calls, 0,
                        results=[{"status": "ok", "preferences_applied": {}}], cart_nonveg=0)
    assert all(c["ok"] for c in good)


def test_cart_lines_min_fails_on_an_emptied_cart():
    got = expectations({"cart_lines_min": 1}, "ok", [], 0, cart_lines=0)
    assert [c["ok"] for c in got] == [False]
    assert [c["ok"] for c in expectations({"cart_lines_min": 1}, "ok", [], 0, cart_lines=2)] == [True]
