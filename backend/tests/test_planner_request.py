"""5a · MealRequest: the planner's input schema (D-029). Pure, no database."""

import pytest

from app.planner.request import MAX_PEOPLE, MealRequest, parse_request

EXAMPLE = {"budget": 1000, "people": 4, "veg_count": 2, "non_spicy_count": 1, "spice_preference": None,
           "meal_type": "dinner", "area": None}


def ok(data) -> MealRequest:
    req, err = parse_request(data)
    assert err is None, err
    return req


def bad(data) -> list[str]:
    req, err = parse_request(data)
    assert req is None and err["status"] == "invalid_input", (req, err)
    return err["problems"]


def test_claude_md_example_parses():
    req = ok(EXAMPLE)
    assert (req.budget, req.people, req.veg_count, req.non_spicy_count, req.meal_type) == (1000, 4, 2, 1, "dinner")
    assert req.missing() == ["area"]


def test_defaults_and_missing_in_ask_order():
    req = ok({})
    assert req.meal_type == "meal" and req.veg_count == 0 and req.non_spicy_veg_count is None
    assert req.missing() == ["people", "budget", "area"]


@pytest.mark.parametrize("field,value", [
    ("budget", "500"), ("budget", 500.0), ("budget", True), ("budget", 0), ("budget", 20_001), ("budget", -5),
    ("people", "2"), ("people", 0), ("people", MAX_PEOPLE + 1), ("people", 2.5), ("people", True),
    ("veg_count", -1), ("veg_count", "1"), ("non_spicy_count", None),
    ("spice_preference", "hot"), ("meal_type", "brunch"), ("meal_type", None), ("area", ""), ("area", "x" * 81),
    ("area", 5),
])
def test_strict_types_refused_not_coerced(field, value):
    problems = bad({**EXAMPLE, field: value})
    assert any(p.startswith(field) for p in problems), problems


def test_unknown_fields_refused():
    assert any("price" in p for p in bad({**EXAMPLE, "price": 10}))
    assert any("user_id" in p for p in bad({**EXAMPLE, "user_id": "x"}))


def test_counts_cannot_exceed_group():
    assert any("veg_count (5)" in p for p in bad({**EXAMPLE, "veg_count": 5}))
    assert any("non_spicy_count (5)" in p for p in bad({**EXAMPLE, "non_spicy_count": 5}))


def test_known_overlap_must_be_possible():
    # 4 people, 3 veg, 3 non-spicy: at least 2 of the non-spicy people must be vegetarian
    assert any("at least 2" in p for p in bad({**EXAMPLE, "veg_count": 3, "non_spicy_count": 3, "non_spicy_veg_count": 1}))
    assert any("can't be more" in p for p in bad({**EXAMPLE, "non_spicy_veg_count": 2}))   # only 1 non-spicy
    assert ok({**EXAMPLE, "veg_count": 3, "non_spicy_count": 3, "non_spicy_veg_count": 2}).overlaps() == range(2, 3)


@pytest.mark.parametrize("people,veg,ns,expected", [
    (4, 2, 1, [0, 1]),          # the non-spicy person may or may not be one of the vegetarians
    (4, 3, 3, [2, 3]),          # at least 2 must overlap
    (3, 3, 1, [1]),             # everyone is veg: the non-spicy person is vegetarian
    (2, 0, 2, [0]),
    (5, 2, 0, [0]),
])
def test_unknown_overlap_covers_every_possibility(people, veg, ns, expected):
    req = ok({"people": people, "veg_count": veg, "non_spicy_count": ns})
    assert list(req.overlaps()) == expected


def test_not_a_dict():
    req, err = parse_request(["budget", 500])
    assert req is None and err["status"] == "invalid_input"


def test_frozen():
    req = ok(EXAMPLE)
    with pytest.raises(Exception):
        req.budget = 5     # type: ignore[misc]
