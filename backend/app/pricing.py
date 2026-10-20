"""Delivery fee, GST and totals (D-025, Option B, approved by Saif). Pure functions, used by the cart, the
orders and the meal planner, so every total in Dawat comes from this one place.

  delivery   ₹25 up to 2 km, + ₹10 for each extra km started; FREE when the branch's items are ≥ ₹499
  GST        5% on food, 18% on the delivery fee
  per branch each branch is its own order (D-020): its own delivery fee and its own GST lines
  rupees     whole rupees; each GST line is rounded half up to the rupee, per branch (an order stores its
             own taxes, so the cart total must be the sum of the orders' totals)
  range      a branch more than MAX_DELIVERY_KM from the delivery point is too far to deliver (the cart
             refuses to add from it, and flags items that end up too far after a delivery change)

Money is integer arithmetic only. Distance is turned into whole metres before the "km started" step, so
floating-point noise (2.0000000001 km) can't add ₹10.
"""

import math

BASE_FEE, BASE_KM, PER_KM_FEE = 25, 2, 10
FREE_DELIVERY_FROM = 499
GST_FOOD_PCT, GST_DELIVERY_PCT = 5, 18
MAX_QTY = 20
MAX_DELIVERY_KM = 8            # Saif, Session 9: beyond this a branch is "too far to deliver" (highest fee ₹85)


def within_delivery_range(distance_km: float) -> bool:
    """8.0 km is in range; measured in whole metres, like the fee."""
    return round(distance_km * 1000) <= MAX_DELIVERY_KM * 1000


def pct_rounded(amount: int, pct: int) -> int:
    """pct% of a whole-rupee amount, rounded half up to the rupee: 5% of ₹370 = 18.5 → ₹19."""
    return (amount * pct + 50) // 100


def delivery_fee(items_total: int, distance_km: float) -> int:
    if items_total >= FREE_DELIVERY_FROM:
        return 0
    metres = round(distance_km * 1000)
    extra_km = max(0, -(-(metres - BASE_KM * 1000) // 1000))       # ceiling division: kilometres started
    return BASE_FEE + PER_KM_FEE * extra_km


def quote_branch(lines: list[dict], distance_km: float) -> dict:
    """lines: [{"price": int, "qty": int}, …] from ONE branch. Returns that branch's bill."""
    if not lines:
        raise ValueError("a branch bill needs at least one line")
    for ln in lines:
        p, q = ln["price"], ln["qty"]
        if isinstance(p, bool) or not isinstance(p, int) or p <= 0:
            raise ValueError(f"price must be a positive whole number of rupees, got {p!r}")
        if isinstance(q, bool) or not isinstance(q, int) or not 1 <= q <= MAX_QTY:
            raise ValueError(f"qty must be a whole number from 1 to {MAX_QTY}, got {q!r}")
    if not isinstance(distance_km, (int, float)) or isinstance(distance_km, bool) or not math.isfinite(distance_km) \
            or distance_km < 0:
        raise ValueError(f"distance_km must be a finite number ≥ 0, got {distance_km!r}")

    items = sum(ln["price"] * ln["qty"] for ln in lines)
    fee = delivery_fee(items, distance_km)
    gst_food, gst_delivery = pct_rounded(items, GST_FOOD_PCT), pct_rounded(fee, GST_DELIVERY_PCT)
    taxes = gst_food + gst_delivery
    return {
        "items_total": items, "distance_km": round(distance_km, 1), "delivery_fee": fee,
        "free_delivery": fee == 0,
        "add_for_free_delivery": 0 if fee == 0 else FREE_DELIVERY_FROM - items,
        "gst_food": gst_food, "gst_delivery": gst_delivery, "taxes": taxes,
        "total": items + fee + taxes,
    }


def quote(branches: list[dict]) -> dict:
    """branches: [{"lines": [...], "distance_km": float, …any other keys are kept}, …]."""
    bills = [{**{k: v for k, v in b.items() if k not in ("lines", "distance_km")},
              **quote_branch(b["lines"], b["distance_km"])} for b in branches]
    return {
        "branches": bills,
        "items_total": sum(b["items_total"] for b in bills),
        "delivery_total": sum(b["delivery_fee"] for b in bills),
        "taxes_total": sum(b["taxes"] for b in bills),
        "grand_total": sum(b["total"] for b in bills),
        "rules": {"delivery": f"₹{BASE_FEE} up to {BASE_KM} km, +₹{PER_KM_FEE} per extra km started, free from "
                              f"₹{FREE_DELIVERY_FROM} per restaurant", "gst": f"{GST_FOOD_PCT}% food, "
                              f"{GST_DELIVERY_PCT}% delivery"},
    }
