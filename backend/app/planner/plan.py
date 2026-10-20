"""plan_meal: the meal planner end to end (Phase 5, D-028, D-029).

  1. validate the request (5a); missing people / budget / area → needs_info (the agent asks, in that order)
  2. resolve the area (same answers as every other tool) and the delivery point
  3. best value = the cheapest plan found within 5 km that fits the budget, from every search (budget-free and
     budgeted, 3 and 5 km); a cheaper plan is never hidden (Saif, Session 12). Best match and variety:
     candidates within 3 km → build → price → score → pick plans different from it (5b–5d); fewer than 3 plans →
     widen to 5 km once (D-028 #6). Nothing cheaper than best value is ever shown.
     The builder is a heuristic, so "cheapest" means the cheapest found (Saif chose this over an exact optimiser).
  4. every plan shown has passed rules.check_plan on facts the checker loaded itself, fresh from the database,
     and its total is the checker's bill (5c)
  5. nothing found within the budget → over_budget with the cheapest plan found at any price, worded as "the
     cheapest I found", and the largest group the budget covers; nothing valid at all → no_valid_plan with the
     rule that blocks it (5e). A rule is never bent.

The planner is deterministic: the same request on the same data gives the same plans and plan_ids, which is how
add_plan_to_cart finds the chosen plan again without trusting a list of items sent back by the LLM.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field

from psycopg import Connection

from app.planner.build import build_plans
from app.planner.candidates import NEAR_KM, WIDE_KM, is_base, is_main, load_candidates
from app.planner.request import MealRequest, parse_request
from app.planner.rules import check_plan, load_facts
from app.tools.preferences import VEG_DIETS, saved_diet
from app.planner.score import Scored, price, score, select, value_order
from app.tools.areas import resolve_area
from app.tools.reference import get_reference

log = logging.getLogger("dawat.planner")
# After this many refusals in one request something is badly wrong with the builder: stop checking (and showing).
MAX_REFUSALS = 10
ROLES = {"best_value": "Best value", "best_match": "Best match", "variety": "Variety"}
WANTED = 3
ASK = {"people": "Ask how many people will eat.",
       "budget": "Ask for the budget in rupees (for the whole bill, delivery and GST included).",
       "area": "Ask which area to deliver to."}


def delivery_point(conn: Connection, area: dict, user_id) -> dict:
    """The user's cart delivery point if it is in this area, else their default address if it is in this area,
    else the area's centre. The same point the cart will use, so the plan total and the cart total agree."""
    row = None
    if user_id is not None:
        row = conn.execute("""
            select a.address_id, a.lat, a.lon from public.carts c join public.addresses a on a.address_id = c.address_id
            where c.user_id = %s and c.status in ('open', 'confirmed') and c.delivery_area_id = %s and a.lat is not null
            order by c.status = 'open' desc, c.created_at desc limit 1""", (user_id, area["area_id"])).fetchone()
        if row is None and not conn.execute("""select 1 from public.carts where user_id = %s and status in ('open',
                'confirmed') and delivery_area_id = %s""", (user_id, area["area_id"])).fetchone():
            row = conn.execute("""select address_id, lat, lon from public.addresses
                                  where user_id = %s and area_id = %s and is_default and lat is not null""",
                               (user_id, area["area_id"])).fetchone()
    if row:
        return {"area_id": area["area_id"], "area": area["name"], "address_id": str(row["address_id"]),
                "lat": row["lat"], "lon": row["lon"]}
    return {"area_id": area["area_id"], "area": area["name"], "address_id": None, "lat": area["lat"], "lon": area["lon"]}


def plan_id(req: MealRequest, delivery: dict, lines: list[dict], total: int) -> str:
    canon = {"r": req.model_dump(exclude={"area"}), "to": [delivery["area_id"], delivery["address_id"],
             round(delivery["lat"], 6), round(delivery["lon"], 6)],
             "l": sorted([ln["item_id"], ln["branch_id"], ln["qty"], ln["price"]] for ln in lines), "t": total}
    return hashlib.sha256(json.dumps(canon, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:20]


@dataclass
class _Ctx:
    """One plan_meal request: the connection, reference data, delivery point, candidate pools loaded once per
    (radius, meal type), built plans and cheapest answers cached per group, how many built plans the checker
    refused, and how many cheaper-than-best-value plans were left out."""
    conn: Connection
    ref: object
    point: tuple[float, float]
    pools: dict = field(default_factory=dict)
    built: dict = field(default_factory=dict)
    scored: dict = field(default_factory=dict)
    caches: dict = field(default_factory=dict)
    cheapest: dict = field(default_factory=dict)
    refused: int = 0


def _verify(ctx: _Ctx, req: MealRequest, s: Scored, radius: float) -> dict | None:
    """The independent check on fresh facts. Returns the checker's result if the plan passes AND every price and
    the total equal the builder's (otherwise prices moved under us: refuse). Refusals are counted."""
    if ctx.refused >= MAX_REFUSALS:
        return None
    result = _check(ctx, req, s, radius)
    if result is None:
        ctx.refused += 1
        log.error("checker refused a built plan (%d this request): %s", ctx.refused, s.key)
    return result


def _check(ctx: _Ctx, req: MealRequest, s: Scored, radius: float) -> dict | None:
    lines = [{"item_id": it.item_id, "branch_id": b.branch_id, "qty": q} for b, it, q in s.plan.lines]
    facts = load_facts(ctx.conn, lines, ctx.point)
    if facts is None or any(f.price != it.price for f, (_, it, _) in zip(facts, s.plan.lines)):
        return None
    result = check_plan(req, facts, radius)
    if not result["ok"] or result["bill"]["grand_total"] != s.total:
        return None
    return result


def _group(req: MealRequest) -> str:
    """The request without its budget and area name: everything the plans built for it depend on."""
    return req.model_dump_json(exclude={"budget", "area"})


def _built(ctx: _Ctx, req: MealRequest, radius: float, budget) -> list[tuple]:
    """[(Plan, bill)] built for this group from the pool at this radius, with this budget (None: no budget);
    cached per request."""
    key = (radius, req.meal_type)
    if key not in ctx.pools:
        ctx.pools[key] = load_candidates(ctx.conn, ctx.ref, ctx.point, radius, req.meal_type)
    bkey = (radius, _group(req), budget)
    if bkey not in ctx.built:
        cache = ctx.caches.setdefault(_group(req), {})
        ctx.built[bkey] = [(p, price(p)) for p in build_plans(req, ctx.pools[key], budget, cache=cache)]
    return ctx.built[bkey]


def _candidates(ctx: _Ctx, req: MealRequest, radius: float, budget) -> list[Scored]:
    """The plans built for this group at this radius (with this budget filter, or None), scored for the request."""
    skey = (radius, _group(req), budget, req.budget)
    if skey not in ctx.scored:
        ctx.scored[skey] = [score(req, p, bill) for p, bill in _built(ctx, req, radius, budget)
                            if budget is None or bill["grand_total"] <= budget]
    return ctx.scored[skey]


def _all_plans(ctx: _Ctx, req: MealRequest, budget) -> list[tuple]:
    """Every plan any search builds for this group within 5 km that fits `budget` (None: any price): the
    budget-free search at 3 and 5 km, plus, with a budget, the budgeted search at 3 and 5 km (it aims at the
    budget, so it finds plans the budget-free search doesn't)."""
    seen: dict[tuple, tuple] = {}
    for b in ((None,) if budget is None else (None, budget)):
        for radius in (NEAR_KM, WIDE_KM):
            for p, bill in _built(ctx, req, radius, b):
                if budget is None or bill["grand_total"] <= budget:
                    seen.setdefault(p.key(), (p, bill))
    return list(seen.values())


def _verified_min(ctx: _Ctx, req: MealRequest, check_req: MealRequest, plans: list[tuple]):
    """(Scored, checker result) for the first plan in value order that the checker passes, or None. Only plans
    tied on (total, restaurants) are scored, to break the tie."""
    ranked = sorted(plans, key=lambda pb: (pb[1]["grand_total"], _n_restaurants(pb[0]), pb[0].key()))
    i = 0
    while i < len(ranked):
        tie = _tie_key(ranked[i])
        j = i
        while j < len(ranked) and _tie_key(ranked[j]) == tie:
            j += 1
        for s in sorted((score(req, p, bill) for p, bill in ranked[i:j]), key=value_order):
            if result := _verify(ctx, check_req, s, WIDE_KM):
                return s, result
        i = j
    return None


def _best_value(ctx: _Ctx, req: MealRequest):
    """Best value (Saif, Session 12): the cheapest plan found within 5 km that fits the budget. Every search's
    plans are looked at and a cheaper one is never hidden, so best value is always the cheapest plan shown, and
    the label is true for everything the planner found. It is not a proof that no cheaper combination exists on
    any menu: the builder is a heuristic (Saif chose to fix the causes the rule-breaker found rather than build an
    exact optimiser; D-029 Session 12 addendum)."""
    key = ("fit", _group(req), req.budget)
    if key not in ctx.cheapest:
        ctx.cheapest[key] = _verified_min(ctx, req, req, _all_plans(ctx, req, req.budget))
    return ctx.cheapest[key]


def _cheapest(ctx: _Ctx, req: MealRequest):
    """The cheapest plan found for this group within 5 km at any price: what an over-budget answer quotes."""
    key = ("any", _group(req))
    if key not in ctx.cheapest:
        unlimited = req.model_copy(update={"budget": NO_LIMIT})
        ctx.cheapest[key] = _verified_min(ctx, req, unlimited, _all_plans(ctx, req, None))
    found = ctx.cheapest[key]
    if found is None:
        return None
    s, result = found
    return score(req, s.plan, s.bill), result          # re-scored for this request's budget (shown parts only)


def _n_restaurants(plan) -> int:
    return len({b.restaurant_id for b, _, _ in plan.lines})


def _tie_key(pb) -> tuple:
    return pb[1]["grand_total"], _n_restaurants(pb[0])


def _pick(ctx: _Ctx, req: MealRequest, cands: list[Scored], radius: float, value):
    vs, vresult = value
    checked: dict[tuple, dict] = {vs.key: vresult}

    def check(s: Scored) -> bool:
        r = _verify(ctx, req, s, radius)
        if r:
            checked[s.key] = r
        return r is not None
    picked, _ = select(cands, check, value=vs)
    return [(role, s, checked[s.key]) for role, s in picked]


def _role_pool(ctx: _Ctx, req: MealRequest, radius: float) -> list[Scored]:
    """Candidates for best match and variety: the budgeted search plus the budget-free plans that fit."""
    out: dict[tuple, Scored] = {}
    for s in _candidates(ctx, req, radius, req.budget) + _candidates(ctx, req, radius, None):
        if s.total <= req.budget:
            out.setdefault(s.key, s)
    return list(out.values())


def _search(ctx: _Ctx, req: MealRequest, value):
    """Best value first, then best match and variety from 3 km, widened to 5 km if fewer than 3 plans
    (D-028 #6). Returns (picked, radius): the radius every shown plan is within."""
    far = max(b.distance_km for b, _, _ in value[0].plan.lines) > NEAR_KM
    picked = _pick(ctx, req, _role_pool(ctx, req, NEAR_KM), NEAR_KM, value)
    if len(picked) >= WANTED:
        return picked, WIDE_KM if far else NEAR_KM
    wide = _pick(ctx, req, _role_pool(ctx, req, WIDE_KM), WIDE_KM, value)
    return (wide if len(wide) >= len(picked) else picked), WIDE_KM


def apply_saved_diet(conn: Connection, req: MealRequest, user_id, diet=...) -> tuple[MealRequest, dict | None]:
    """A signed-in user whose saved diet is vegetarian (or eggetarian) is one of the vegetarians in their own plan
    (Saif, Session 16, D-039): veg_count is at least 1. A known overlap that no longer fits is dropped (the plan then
    works whoever the non-spicy people are)."""
    if diet is ...:                                   # the chat passes its turn-start snapshot (D-044)
        diet = saved_diet(conn, user_id)
    if diet not in VEG_DIETS or req.veg_count >= 1:
        return req, None
    data = req.model_dump() | {"veg_count": 1}
    new, err = parse_request(data)
    if err:
        new, err = parse_request(data | {"non_spicy_veg_count": None})
    if err:
        return req, None
    return new, {"diet": diet, "veg_count": {"asked": req.veg_count, "used": 1},
                 "message": f"The user's saved diet is {diet}, so they are counted as one of the vegetarians: every "
                            "plan has a vegetarian main for them. Tell the user this in one short line."}


def plan_meal(conn: Connection, request, user_id=None, diet=...) -> dict:
    req, err = parse_request(request)
    if err:
        return err
    req, applied = apply_saved_diet(conn, req, user_id, diet)
    understood = req.model_dump()
    if missing := req.missing():
        return {"status": "needs_info", "missing": missing, "understood": understood,
                **({"preferences_applied": applied} if applied else {}),
                "message": ASK[missing[0]] + " Do not suggest dishes or prices yet."}
    ref = get_reference(conn)
    resolved = resolve_area(ref, req.area)
    if resolved["status"] != "ok":
        return {"status": resolved["status"], "understood": understood, "area_resolution": resolved,
                "message": resolved["message"]}
    area = ref.areas[resolved["area"]["area_id"]]
    delivery = delivery_point(conn, area, user_id)
    ctx = _Ctx(conn, ref, (delivery["lat"], delivery["lon"]))
    base = {"understood": understood, "delivery": delivery,
            **({"area_note": resolved["message"]} if resolved["matched_by"] == "fuzzy" else {}),
            **({"preferences_applied": applied} if applied else {})}

    value = _best_value(ctx, req)
    if ctx.refused >= MAX_REFUSALS:
        return planner_error(base, ctx)
    if value is None:                        # nothing found within the budget, by any search
        cheapest = _cheapest(ctx, req)
        if ctx.refused >= MAX_REFUSALS:
            return planner_error(base, ctx)
        if cheapest is None:
            return no_valid_plan(ctx, req, base)
        out = impossible(ctx, req, delivery, base, cheapest)
        return planner_error(base, ctx) if ctx.refused >= MAX_REFUSALS else out
    picked, radius = _search(ctx, req, value)
    return _ok(req, picked, radius, base, ctx)


def _ok(req: MealRequest, picked, radius: float, base: dict, ctx: _Ctx) -> dict:
    plans = [plan_json(req, role, s, result, base["delivery"]) for role, s, result in picked]
    return {"status": "ok", **base, "radius_km": radius, "plans": plans,
            "planner": {"refused_by_checker": ctx.refused},
            "message": ("Show these plans as options, with each total exactly as given, and copy each plan's "
                        "diet_note line under it word for word; never change an item, a quantity or a price. " + ("Only %d genuinely different plan%s fit. " % (
                            len(plans), "" if len(plans) == 1 else "s") if len(plans) < WANTED else "") +
                        "When the user picks one, call add_plan_to_cart with the same request and its plan_id.")}


def planner_error(base: dict, ctx: _Ctx) -> dict:
    """The checker kept refusing what the builder made: a bug. Say so honestly; never fall back to showing plans or
    claiming the request is impossible."""
    return {"status": "planner_error", **base, "planner": {"refused_by_checker": ctx.refused},
            "message": "Dawat AI couldn't put together a safe plan just now. Apologise, say it's on our side, and "
                       "offer to search dishes or restaurants instead. Do not suggest any plan or price."}


# --- 5e: impossible requests ---------------------------------------------------------------------------------
NO_LIMIT = 10 ** 9


def no_valid_plan(ctx: _Ctx, req: MealRequest, base: dict) -> dict:
    return {"status": "no_valid_plan", **base, "radius_km": WIDE_KM, "planner": {"refused_by_checker": ctx.refused},
            "reasons": diagnose(ctx.conn, ctx.ref, req, ctx.point),
            "message": "No plan can meet these rules from restaurants near this delivery point, at any price. "
                       "Tell the user which rule blocks it (reasons) and ask whether to change the request. "
                       "Never suggest a plan that breaks a rule."}


def impossible(ctx: _Ctx, req: MealRequest, delivery: dict, base: dict, cheapest) -> dict:
    """Nothing found within the budget. Quote the cheapest plan found at any price ("the cheapest I found": the
    builder is a heuristic), and the largest smaller group whose best value fits, exactly as planning for that
    group would show it."""
    unlimited = req.model_copy(update={"budget": NO_LIMIT})
    s, result = cheapest
    smaller = None
    # A strict lower bound skips sizes that can't fit: p people need p portions, each at least the cheapest price
    # per portion of any main within 5 km (delivery and GST only add). It never changes the answer, only time.
    pool = ctx.pools.get((WIDE_KM, req.meal_type)) or []
    per_portion = min((i.price / i.serves for b in pool for i in b.mains), default=0)
    for p in range(req.people - 1, 0, -1):
        if p * per_portion > req.budget:
            continue
        smaller_req = MealRequest(budget=req.budget, people=p, veg_count=min(req.veg_count, p),
                                  non_spicy_count=min(req.non_spicy_count, p), spice_preference=req.spice_preference,
                                  meal_type=req.meal_type, area=req.area)
        found = _best_value(ctx, smaller_req)               # exactly the best value planning for p people shows
        if found:
            smaller = {"people": p, "veg_count": smaller_req.veg_count, "non_spicy_count": smaller_req.non_spicy_count,
                       "cheapest_total": found[0].total}
            break
    cheapest_json = plan_json(unlimited, "cheapest_valid", s, result, delivery)
    cheapest_json.pop("plan_id")                      # over budget: it can't be added as "the plan for this request"
    return {"status": "over_budget", **base, "radius_km": WIDE_KM, "budget": req.budget,
            "planner": {"refused_by_checker": ctx.refused},
            "cheapest_total": s.total, "short_by": s.total - req.budget, "cheapest_plan": cheapest_json,
            "largest_group_within_budget": smaller,
            "message": (f"I couldn't find a plan within ₹{req.budget}: the cheapest plan I found that meets "
                        f"every rule costs ₹{s.total} (₹{s.total - req.budget} more), delivery and GST included. "
                        "Say it in those words (the cheapest you found, not that nothing can exist). Offer to "
                        "raise the budget to that amount" + (
                            f", or to plan for {smaller['people']} {'person' if smaller['people'] == 1 else 'people'} "
                            f"(from ₹{smaller['cheapest_total']})" if smaller else "") +
                        ". Never drop a rule to fit the budget.")}


def diagnose(conn, ref, req: MealRequest, point) -> list[dict]:
    pool = load_candidates(conn, ref, point, WIDE_KM, req.meal_type)
    if not pool:
        what = "restaurants that serve a full meal" if req.meal_type in ("lunch", "dinner", "meal") else \
            f"restaurants serving {req.meal_type}"
        return [{"rule": "places", "detail": f"no open {what} within {WIDE_KM:g} km"}]
    reasons = []
    mains = [i for b in pool for i in b.mains]
    if req.veg_count and not any(i.is_veg for i in mains):
        reasons.append({"rule": "diet", "detail": "no vegetarian main nearby"})
    if req.non_spicy_count and not any(i.mild for i in mains):
        reasons.append({"rule": "diet", "detail": "no main with spice ≤ 1 nearby"})
    if req.veg_count and req.non_spicy_count and not any(i.mild and i.is_veg for i in mains):
        reasons.append({"rule": "diet", "detail": "no mild vegetarian main nearby"})
    low, high = req.spice_range()
    if req.spice_preference and req.non_spicy_count < req.people:
        fits = [i for i in mains if low <= i.spice_level <= high]
        if not fits:
            reasons.append({"rule": "spice", "detail": f"no main nearby is '{req.spice_preference}' "
                                                       f"(spice {low}–{high})"})
        elif req.veg_count > req.overlaps()[-1] and not any(i.is_veg for i in fits):
            reasons.append({"rule": "spice", "detail": f"no vegetarian main nearby is '{req.spice_preference}' "
                                                       f"(spice {low}–{high})"})
    return reasons or [{"rule": "meal", "detail": "no restaurant nearby can make a complete plan for this group"}]


# ─── the JSON a plan is shown as ─────────────────────────────────────────────────────────────────────────────
def _line_role(req: MealRequest, it) -> str:
    if is_main(it, req.meal_type):
        return "main"
    return "bread or rice" if is_base(it) else "side"


def plan_json(req: MealRequest, role: str, s: Scored, result: dict, delivery: dict) -> dict:
    bill = result["bill"]                                    # the checker's bill, from fresh prices
    by_branch: dict[str, dict] = {}
    flat = []
    for b, it, q in s.plan.lines:
        e = by_branch.setdefault(b.branch_id, {
            "restaurant": b.restaurant, "restaurant_id": b.restaurant_id, "branch_id": b.branch_id,
            "branch_label": b.label, "branch_area": b.area, "distance_km": round(b.distance_km, 1), "items": []})
        e["items"].append({"item_id": it.item_id, "name": it.name, "qty": q, "price": it.price,
                           "line_total": it.price * q, "is_veg": it.is_veg, "spice_level": it.spice_level,
                           "serves": it.serves, "category": it.category, "role": _line_role(req, it)})
        flat.append({"item_id": it.item_id, "branch_id": b.branch_id, "qty": q, "price": it.price})
    for bb in bill["branches"]:
        e = by_branch[bb["branch_id"]]
        e.update({k: bb[k] for k in ("items_total", "delivery_fee", "free_delivery", "taxes", "total")})
    total = bill["grand_total"]
    out = {"role": role, "label": ROLES.get(role, "Cheapest valid plan"),
           "plan_id": plan_id(req, delivery, flat, total), "restaurants": list(by_branch.values()),
           "items_total": bill["items_total"], "delivery_total": bill["delivery_total"],
           "taxes_total": bill["taxes_total"], "grand_total": total,
           "diet_note": diet_note(req, result["portions"]), "score": s.parts}
    if req.budget and req.budget < NO_LIMIT:
        out["budget_left"] = req.budget - total
        out["budget_used_pct"] = round(100 * total / req.budget)
    return out


def diet_note(req: MealRequest, kinds: dict[str, int]) -> str:
    veg = kinds["veg_mild"] + kinds["veg_spicy"]
    mild = kinds["veg_mild"] + kinds["nonveg_mild"]
    total = sum(kinds.values())
    parts = [f"{total} main portion{'s' * (total != 1)} for {req.people}"]
    if req.veg_count:
        parts.append(f"{veg} veg for {req.veg_count} vegetarian{'s' * (req.veg_count != 1)}")
    if req.non_spicy_count:
        parts.append(f"{mild} mild (spice ≤ 1) for {req.non_spicy_count} non-spicy")
    tolerant = req.people - req.non_spicy_count
    if req.spice_preference and tolerant:
        low, high = req.spice_range()
        levels = f"spice {low}" if low == high else f"spice {low}–{high}"
        parts.append(f"{req.spice_preference} ({levels}) for {'everyone' if tolerant == req.people else tolerant}"
                     f"{'' if tolerant == req.people else ' who eat spicy food'}, as asked")
    note = "; ".join(parts) + "."
    if req.veg_count and req.non_spicy_count and req.non_spicy_veg_count is None \
            and len(req.overlaps()) > 1:
        note += (f" Works whoever the non-spicy {'person is' if req.non_spicy_count == 1 else 'people are'} "
                 "(checked for every case).")
    return note
