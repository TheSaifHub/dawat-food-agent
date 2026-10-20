"""Delivery fee, GST and totals (D-025): the approved examples, the edges, and properties over random carts."""

import pytest
from hypothesis import given, settings, strategies as st

from app.pricing import (FREE_DELIVERY_FROM, MAX_QTY, delivery_fee, pct_rounded, quote, quote_branch)


# ── the carts Saif approved Option B on (real menu prices and distances, Session 9) ──
@pytest.mark.parametrize("lines, km, total, fee", [
    ([(370, 1)], 0.0, 419, 25),     # Chicken Dum Biryani, Hi-Tech Bawarchi → Madhapur
    ([(200, 1)], 1.6, 240, 25),     # Paneer Burger, Burger King → Madhapur
    ([(200, 1)], 2.7, 251, 35),     # Paneer Tikka Sandwich, Kaficko → Madhapur
    ([(350, 2)], 0.1, 735, 0),      # 2 × Chicken Dum Biryani, Paradise → Kukatpally (free delivery)
    ([(30, 1)], 0.3, 62, 25),       # Masala Chai, Imroze Cafe → Ameerpet
])
def test_approved_examples(lines, km, total, fee):
    b = quote_branch([{"price": p, "qty": q} for p, q in lines], km)
    assert (b["total"], b["delivery_fee"]) == (total, fee)


def test_two_restaurants_pay_two_fees_and_round_per_restaurant():
    """Kritunga ₹340 + Chick King ₹190, both 0.0 km: 25 + 25 delivery; GST per restaurant 17+5 and 10+5 (each
    line rounded half up) = ₹617. (₹616 was shown when GST was rounded across the cart; D-025.)"""
    q = quote([{"lines": [{"price": 340, "qty": 1}], "distance_km": 0.0},
               {"lines": [{"price": 190, "qty": 1}], "distance_km": 0.0}])
    assert q["delivery_total"] == 50 and q["taxes_total"] == 37 and q["grand_total"] == 617


# ── edges ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("km, fee", [(0, 25), (2.0, 25), (2.0000000001, 25), (2.0004, 25), (2.0006, 35), (2.01, 35),
                                     (3.0, 35), (3.001, 45), (10.2, 115)])
def test_kilometres_started(km, fee):
    assert delivery_fee(100, km) == fee


@pytest.mark.parametrize("items, near_fee, far_fee", [(498, 25, 55), (FREE_DELIVERY_FROM, 0, 0), (500, 0, 0),
                                                      (10_000, 0, 0)])
def test_free_delivery_from_499_at_any_distance(items, near_fee, far_fee):
    assert (delivery_fee(items, 0), delivery_fee(items, 5.0)) == (near_fee, far_fee)


@pytest.mark.parametrize("amount, pct, out", [(370, 5, 19), (360, 5, 18), (350, 5, 18), (30, 5, 2), (25, 18, 5),
                                              (35, 18, 6), (0, 18, 0), (1, 5, 0), (10, 5, 1)])
def test_gst_rounds_half_up(amount, pct, out):
    assert pct_rounded(amount, pct) == out


def test_add_for_free_delivery_is_what_is_missing():
    assert quote_branch([{"price": 300, "qty": 1}], 1.0)["add_for_free_delivery"] == 199
    assert quote_branch([{"price": 300, "qty": 2}], 1.0)["add_for_free_delivery"] == 0


@pytest.mark.parametrize("line, km", [({"price": 0, "qty": 1}, 1), ({"price": -5, "qty": 1}, 1), ({"price": 10.5, "qty": 1}, 1),
                                      ({"price": True, "qty": 1}, 1), ({"price": 100, "qty": 0}, 1),
                                      ({"price": 100, "qty": MAX_QTY + 1}, 1), ({"price": 100, "qty": 1.0}, 1),
                                      ({"price": 100, "qty": 1}, -1), ({"price": 100, "qty": 1}, float("nan")),
                                      ({"price": 100, "qty": 1}, float("inf"))])
def test_bad_lines_are_refused(line, km):
    with pytest.raises(ValueError):
        quote_branch([line], km)


def test_empty_branch_is_refused():
    with pytest.raises(ValueError):
        quote_branch([], 1.0)


# ── properties over random carts ─────────────────────────────────────────
line = st.fixed_dictionaries({"price": st.integers(1, 1500), "qty": st.integers(1, MAX_QTY)})
branch = st.fixed_dictionaries({"lines": st.lists(line, min_size=1, max_size=6),
                                "distance_km": st.floats(0, 40, allow_nan=False)})


@settings(max_examples=500, deadline=None)
@given(st.lists(branch, min_size=1, max_size=4))
def test_totals_always_add_up(branches):
    q = quote(branches)
    for b, src in zip(q["branches"], branches):
        items = sum(ln["price"] * ln["qty"] for ln in src["lines"])
        assert b["items_total"] == items
        assert b["total"] == b["items_total"] + b["delivery_fee"] + b["taxes"]       # the orders table CHECK
        assert b["taxes"] == b["gst_food"] + b["gst_delivery"]
        assert all(isinstance(b[k], int) and b[k] >= 0 for k in ("delivery_fee", "taxes", "total"))
        assert (b["delivery_fee"] == 0) == (items >= FREE_DELIVERY_FROM)
        assert abs(b["gst_food"] - items * 0.05) <= 0.5 and abs(b["gst_delivery"] - b["delivery_fee"] * 0.18) <= 0.5
    assert q["grand_total"] == sum(b["total"] for b in q["branches"])
    assert q["grand_total"] == q["items_total"] + q["delivery_total"] + q["taxes_total"]


@settings(max_examples=300, deadline=None)
@given(st.integers(1, FREE_DELIVERY_FROM - 1), st.floats(0, 40, allow_nan=False), st.floats(0, 40, allow_nan=False))
def test_further_never_costs_less(items, a, b):
    near, far = sorted((a, b))
    assert delivery_fee(items, near) <= delivery_fee(items, far)


# ── delivery range (Saif, D-025: 8 km) ───────────────────────────────────
@pytest.mark.parametrize("km, ok", [(0, True), (7.99, True), (8.0, True), (8.0004, True), (8.0006, False), (8.01, False),
                                    (42.6, False)])
def test_delivery_range_is_8_km(km, ok):
    from app.pricing import within_delivery_range
    assert within_delivery_range(km) is ok
