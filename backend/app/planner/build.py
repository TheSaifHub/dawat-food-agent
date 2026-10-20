"""5c · The combo builder: candidate plans for a MealRequest from a candidate pool (D-029).

How a plan is built, per restaurant:
  1. Portion mixes. A mix says how many main portions of each kind to buy: veg mild, veg spicy, non-veg mild,
     non-veg spicy, adding up to the group size. Only mixes that feed every eater whoever the non-spicy people
     are (a greedy count, see feeds_everyone) are kept. A whole-veg group only gets veg kinds; a whole-non-spicy
     group only mild kinds.
  2. Fills. Each kind's portions are filled from the restaurant's mains of that kind, in three styles:
       value    the cheapest way to get the portions (a small knapsack: a "Full" serves-2 biryani can beat two)
       match    the dishes closest to the spice preference, alternating the top two for a group
       variety  as many different dishes as possible, cheapest first
  3. For each style, the best few mixes per restaurant that can actually be built are kept (by estimated cost,
     preference fit or variety), so the work stays small even with 340 restaurants in range. For value, the 8 cheapest by estimate are built in
     full and ranked by their real total (bread, sides, delivery and GST change the order).
  4. Trim: any main unit that can be taken away with everyone still fed is taken away (never padded, D-028 #3).
  5. A proper meal (D-028 #2): every curry gets bread or rice from the same restaurant; other mains that aren't
     a complete plate (biryani, mandi, meals) get their paired side (sambar with idli, garlic bread with pizza),
     one per two portions. Sides prefer veg + mild,
     so anyone at the table can share them. Desserts and drinks are never added.
Two-restaurant plans (D-028 #7, at most 2): vegetarians' portions from one place and the rest from another, from
the few cheapest restaurants for each part.

Nothing here is trusted: plan.py runs every plan through rules.check_plan before it can be shown.
"""

from dataclasses import dataclass
from itertools import product
from math import ceil

from app.planner.candidates import COMPLETE_MAINS, Branch, Item
from app.planner.request import MealRequest
from app.planner.score import price, spice_fit
from app.pricing import MAX_QTY

KINDS = ("veg_mild", "veg_spicy", "nonveg_mild", "nonveg_spicy")
STYLES = ("value", "match", "match_dear", "variety")
KEEP_PER_STYLE = 2                  # mixes kept per restaurant per style
VALUE_SHORTLIST = 8                 # value style: mixes built in full per restaurant, then ranked by real total
PAIR_TOP = 5                        # restaurants per part when pairing two restaurants
CHEAP_BREAD_MAX = 60                # a roti/naan at or under this price: two per curry portion


def kind(item: Item) -> str:
    return ("veg_" if item.is_veg else "nonveg_") + ("mild" if item.mild else "spicy")


@dataclass
class Plan:
    lines: list[tuple[Branch, Item, int]]
    style: str
    two_restaurants: bool = False
    bill: dict | None = None            # score.price() fills it once

    def key(self) -> tuple:
        return tuple(sorted((i.item_id, b.branch_id, q) for b, i, q in self.lines))


# ─── 1. portion mixes ────────────────────────────────────────────────────────────────────────────────────────
def feeds_everyone(req: MealRequest, mix: dict[str, int]) -> bool:
    """Greedy check, for every possible overlap: the veg-mild eaters take veg-mild portions; veg-any eaters take
    veg-spicy then leftover veg-mild; non-veg-mild eaters take non-veg-mild then leftover veg-mild; everyone else
    takes anything. (The checker uses a different method, Hall's condition, on purpose.)"""
    if sum(mix.values()) < req.people:
        return False
    low, high = req.spice_range()
    for k in req.overlaps():
        vm, vs, nm = k, req.veg_count - k, req.non_spicy_count - k
        na = req.people - req.veg_count - req.non_spicy_count + k
        if low >= 2:            # "spicy"/"medium": mild portions only for the non-spicy, spicy ones for the rest
            if mix["veg_mild"] < vm or mix["veg_mild"] + mix["nonveg_mild"] < vm + nm or \
                    mix["veg_spicy"] < vs or mix["veg_spicy"] + mix["nonveg_spicy"] < vs + na:
                return False
            continue
        if high <= 1:           # "mild": everyone eats mild
            vm, vs, nm = vm + vs, 0, nm + na
        spare = mix["veg_mild"] - vm
        if spare < 0 or max(0, vs - mix["veg_spicy"]) + max(0, nm - mix["nonveg_mild"]) > spare:
            return False
    return True


def in_range(req: MealRequest, item: Item) -> bool:
    """No item above the stated preference's top level (very spicy for "medium", above 1 for "mild")."""
    return item.spice_level <= req.spice_range()[1]


def portion_mixes(req: MealRequest) -> list[dict[str, int]]:
    low, high = req.spice_range()
    allowed = [k for k in KINDS if not (req.veg_count == req.people and k.startswith("nonveg"))
               and not ((req.non_spicy_count == req.people or high <= 1) and k.endswith("spicy"))
               and not (low >= 2 and req.non_spicy_count == 0 and k.endswith("mild"))]
    out = []
    for counts in product(range(req.people + 1), repeat=len(allowed)):
        if sum(counts) != req.people:
            continue
        mix = dict.fromkeys(KINDS, 0) | dict(zip(allowed, counts))
        if feeds_everyone(req, mix):
            out.append(mix)
    return out


# ─── 2. fills ────────────────────────────────────────────────────────────────────────────────────────────────
def fill_value(items: list[Item], n: int, extra=lambda it: 0) -> list[tuple[Item, int]] | None:
    """Cheapest way to get at least n portions (unbounded knapsack over 0..n portions). `extra(item)` is what one
    portion of it costs in bread/rice/side, so a dal that needs rotis isn't mistaken for the cheaper main."""
    if not items:
        return None
    best: list[tuple[int, tuple]] = [(0, ())] + [(10 ** 9, ())] * n
    for p in range(1, n + 1):
        for it in items:
            prev = best[max(0, p - it.serves)]
            cand = (prev[0] + it.price + extra(it) * it.serves, prev[1] + (it,))
            if cand[0] < best[p][0] or (cand[0] == best[p][0] and len(cand[1]) < len(best[p][1])):
                best[p] = cand
    return _count(best[n][1])


def fill_ordered(items: list[Item], n: int, alternate: int) -> list[tuple[Item, int]] | None:
    """Take items in the given order, cycling through the first `alternate` of them, until n portions."""
    if not items:
        return None
    pool, got, chosen, i = items[:max(1, alternate)], 0, [], 0
    while got < n:
        it = pool[i % len(pool)]
        chosen.append(it)
        got += it.serves
        i += 1
    return _count(tuple(chosen))


def _count(chosen: tuple) -> list[tuple[Item, int]]:
    out: dict[str, list] = {}
    for it in chosen:
        out.setdefault(it.item_id, [it, 0])[1] += 1
    return [(it, q) for it, q in out.values()]


def fills_for(branch: Branch, req: MealRequest, style: str, kind_name: str, n: int, cache: dict | None = None):
    items = [i for i in branch.mains if kind(i) == kind_name and in_range(req, i)]
    if n == 0:
        return []
    if style == "value":
        return fill_value(items, n, lambda it: accompaniment_cost(req, branch, it, cache))
    if style in ("match", "match_dear"):
        sign = 1 if style == "match" else -1
        ordered = sorted(items, key=lambda i: (-spice_fit(i.spice_level, req.spice_preference), sign * i.price, i.item_id))
        return fill_ordered(ordered, n, alternate=2 if n >= 2 else 1)
    ordered = sorted(items, key=lambda i: (i.price, i.item_id))                    # variety
    return fill_ordered(ordered, n, alternate=min(n, 2))         # ≤ 2 dishes per kind: ≤ 8 in a plan


FAR_TOO_DEAR = 10 ** 6          # a main whose meal can't be completed here: ranked last (assembly drops it)


def accompaniment_cost(req: MealRequest, branch: Branch, item: Item, cache: dict | None = None) -> int:
    """Estimated bread/rice/side cost per portion of a main, mirroring complete_meal: a curry's base (2 cheap rotis
    or 1 dearer base), or half the cheapest paired side (one per two portions). For ranking only. It depends only
    on the branch and the main's category, so it is worked out once per pair (`cache`)."""
    if req.meal_type not in ("lunch", "dinner", "meal") or item.category in COMPLETE_MAINS:
        return 0
    if cache is None:
        return _accompaniment(req, branch, item)
    key = ("acc", branch.branch_id, item.category)
    if key not in cache:
        cache[key] = _accompaniment(req, branch, item)
    return cache[key]


def _accompaniment(req: MealRequest, branch: Branch, item: Item) -> int:
    if item.category == "curry":
        bases = [i for i in branch.bases if _side_ok(req, i)]
        if not bases:
            return FAR_TOO_DEAR
        return min(i.price * (2 if i.category == "bread" and i.price <= CHEAP_BREAD_MAX else 1) for i in bases)
    sides = [i for i in branch.sides if _side_ok(req, i)]
    if item.category in SIDE_PAIRING:
        sides = [i for i in sides if side_rank(item.category, i) < NO_PAIR]
    return min((i.price for i in sides), default=2 * FAR_TOO_DEAR) // 2


# ─── 4. trim, 5. complete the meal ───────────────────────────────────────────────────────────────────────────
def trim(req: MealRequest, mains: list[tuple[Branch, Item, int]]) -> list[tuple[Branch, Item, int]]:
    """Take away main units, dearest first, while everyone is still fed."""
    lines = [list(x) for x in mains]
    changed = True
    while changed:
        changed = False
        for ln in sorted(lines, key=lambda x: (-x[1].price, x[1].item_id)):
            ln[2] -= 1
            mix = dict.fromkeys(KINDS, 0)
            for _, it, q in lines:
                mix[kind(it)] += it.serves * q
            if feeds_everyone(req, mix):
                changed = True
                lines = [x for x in lines if x[2] > 0]
                break
            ln[2] += 1
    return [tuple(x) for x in lines]


# The side that goes with the main (D-029): sambar with idli, garlic bread with pizza, fries with fried chicken,
# manchurian with fried rice. Anything else is a fallback. (category, name word or None), best first. Only proper
# meal mains need one (burgers, rolls and the like are never a lunch/dinner main, Session 12).
SIDE_PAIRING = {
    "tiffin": [("curry", None)],
    "pizza": [("bread", "garlic"), ("salad", None), ("snack", None)],
    "pasta": [("bread", "garlic"), ("salad", None), ("soup", None)],
    "fried_chicken": [("snack", None), ("salad", None)], "mexican": [("mexican", None), ("snack", None)],
    "noodles": [("starter", None), ("soup", None)], "rice": [("curry", None), ("starter", None), ("soup", None)],
    "kebab": [("bread", None), ("salad", None)], "continental": [("continental", None), ("salad", None), ("soup", None)],
}


NO_PAIR = 99


def side_rank(main_category: str, side: Item) -> int:
    for rank, (cat, word) in enumerate(SIDE_PAIRING.get(main_category, [])):
        if side.category == cat and (word is None or word in side.name.lower()):
            return rank
    return NO_PAIR


def _side_ok(req: MealRequest, it: Item) -> bool:
    return (it.is_veg or req.veg_count < req.people) and (it.mild or req.non_spicy_count < req.people) \
        and in_range(req, it)


def complete_meal(req: MealRequest, mains: list[tuple[Branch, Item, int]], style: str):
    """Add bread/rice for curries and a side if a full meal needs one. None if the meal can't be completed."""
    lines = list(mains)
    if req.meal_type not in ("lunch", "dinner", "meal"):
        return lines
    branches = {b.branch_id: b for b, _, _ in mains}
    for bid, b in branches.items():
        curry = sum(it.serves * q for bb, it, q in mains if bb.branch_id == bid and it.category == "curry")
        if not curry:
            continue
        bases = [i for i in b.bases if _side_ok(req, i)]
        if not bases:
            return None
        if style == "value":
            base = min(bases, key=lambda i: (i.price * (2 if i.category == "bread" and i.price <= CHEAP_BREAD_MAX else 1),
                                              i.item_id))
        else:
            breads = [i for i in bases if i.category == "bread"]
            base = min(breads or bases, key=lambda i: (i.price, i.item_id))
        per = 2 if base.category == "bread" and base.price <= CHEAP_BREAD_MAX else 1
        lines.append((b, base, min(MAX_QTY, per * curry)))
    # Stricter than the checker's minimum on purpose: every main that is neither a complete plate (biryani, mandi,
    # meals) nor a curry (which got its bread/rice above) gets its paired side, shared between two.
    others = [(b, it, q) for b, it, q in mains if it.category not in COMPLETE_MAINS and it.category != "curry"]
    if others:
        b = max(branches.values(), key=lambda b: (sum(it.serves * q for bb, it, q in others if bb is b), b.branch_id))
        mine = [(it, q) for bb, it, q in others if bb is b]
        main_cat = max((sum(it.serves * q for it, q in mine if it.category == c), c) for c in {it.category for it, _ in mine})[1]
        sides = [i for i in b.sides if _side_ok(req, i)]
        if main_cat in SIDE_PAIRING:          # a known pairing and none of its sides here: skip, don't mismatch
            sides = [i for i in sides if side_rank(main_cat, i) < NO_PAIR]
        if not sides:
            return None
        if style == "value":            # any matching side will do: the cheapest (Rasam over Sambar if cheaper)
            side = min(sides, key=lambda i: (i.price, side_rank(main_cat, i), not i.is_veg, not i.mild, i.item_id))
        else:                           # the best match, veg and mild first so anyone at the table can share it
            side = min(sides, key=lambda i: (side_rank(main_cat, i), not i.is_veg, not i.mild, i.price, i.item_id))
        portions = sum(it.serves * q for _, it, q in others)
        lines.append((b, side, min(MAX_QTY, ceil(portions / 2))))
    return merge(lines)


def merge(lines: list[tuple[Branch, Item, int]]) -> list[tuple[Branch, Item, int]]:
    """One line per item per branch: the same bread can be a curry's base AND a kebab's side."""
    out: dict[tuple[str, str], list] = {}
    for b, it, q in lines:
        e = out.setdefault((b.branch_id, it.item_id), [b, it, 0])
        e[2] = min(MAX_QTY, e[2] + q)
    return [tuple(e) for e in out.values()]


# ─── 3. per restaurant, and pairs ────────────────────────────────────────────────────────────────────────────
def _assemble(req: MealRequest, parts: list[tuple[Branch, dict[str, int]]], style: str, fills_cache: dict):
    mains = []
    for b, mix in parts:
        for kname, n in mix.items():
            if n == 0:
                continue
            key = (b.branch_id, style, kname, n)
            if key not in fills_cache:
                fills_cache[key] = fills_for(b, req, style, kname, n, fills_cache)
            f = fills_cache[key]
            if f is None:
                return None
            mains += [(b, it, q) for it, q in f]
    if not mains:
        return None
    lines = complete_meal(req, trim(req, mains), style)
    if lines is None:
        return None
    return Plan(lines, style, two_restaurants=len({b.branch_id for b, _, _ in lines}) > 1)


def _estimate(req: MealRequest, b: Branch, mix: dict[str, int], style: str, cache: dict):
    """(mains cost, preference fit, distinct dishes, mains + estimated bread/sides cost) of a mix at one branch, or
    None if it can't be filled. The budget filter uses the mains cost, a lower bound of the real items total.
    Nothing here depends on the budget, so it is cached across the builds of one request."""
    ekey = ("est", b.branch_id, style, tuple(mix.values()))
    if ekey not in cache:
        cache[ekey] = _estimate_uncached(req, b, mix, style, cache)
    return cache[ekey]


def _estimate_uncached(req: MealRequest, b: Branch, mix: dict[str, int], style: str, cache: dict):
    cost, fit, dishes, portions, mains = 0, 0.0, set(), 0, []
    for kname, n in mix.items():
        if n == 0:
            continue
        key = (b.branch_id, style, kname, n)
        if key not in cache:
            cache[key] = fills_for(b, req, style, kname, n, cache)
        f = cache[key]
        if f is None:
            return None
        for it, q in f:
            cost += it.price * q
            mains.append((b, it, q))
            fit += spice_fit(it.spice_level, req.spice_preference) * it.serves * q
            portions += it.serves * q
            dishes.add(it.dish_id)
    nonveg = mix["nonveg_mild"] + mix["nonveg_spicy"]
    diet = 1.0 if req.people == req.veg_count else min(nonveg, req.people - req.veg_count) / (req.people - req.veg_count)
    # Exactly the bread/rice/side lines complete_meal would add (Session 12 rule-breaker: "half a side per portion"
    # made one plate of fried rice look cheaper than dal + 2 rotis, though that plate pays for a whole raita).
    lines = complete_meal(req, mains, style)
    with_sides = sum(it.price * q for _, it, q in lines) if lines is not None else 10 ** 9
    return cost, fit / max(1, portions) + 0.5 * diet, len(dishes), with_sides


def build_plans(req: MealRequest, pool: list[Branch], budget: int | None, pairs: bool = True,
                styles: tuple[str, ...] = STYLES, cache: dict | None = None) -> list[Plan]:
    """`cache` may be shared by several builds for the SAME group (the request without its budget): fills,
    estimates, side costs and assembled plans don't depend on the budget or on which pool a branch came from."""
    mixes = portion_mixes(req)
    cache = {} if cache is None else cache
    group = req.model_dump_json(exclude={"budget", "area"})
    if cache.setdefault("group", group) != group:        # side costs and fills differ between groups: never share
        raise ValueError("a build cache was shared between two different groups")
    plans: dict[tuple, Plan] = {}

    def add(plan: Plan | None):
        if plan is not None and plan.key() not in plans:
            plans[plan.key()] = plan

    for b in pool:
        for style in styles:
            scored = []
            for mix in mixes:
                est = _estimate(req, b, mix, style, cache)
                if est is None or (budget is not None and est[0] > budget):
                    continue
                cost, fit, distinct, with_sides = est
                if style == "value":
                    rank = (with_sides, cost)
                elif style == "variety":
                    rank = (-distinct, cost)
                else:   # match: best fit, then closest to 90% of the budget (or cheapest if no budget)
                    rank = (-round(fit, 6), abs(cost - 0.9 * budget) if budget else cost)
                scored.append((rank, tuple(mix.values()), mix))
            if style == "value":
                # The mains-only estimate misranks (dal ₹170 looks cheaper than biryani ₹210 until its rotis are
                # added), so the shortlist is built in full and ranked by the real total, delivery and GST included.
                built = _first_built(req, b, sorted(scored), style, cache, VALUE_SHORTLIST)
                built += [v for p in built for v in free_delivery_variants(req, b, p)]
                built = [(price(p)["grand_total"], p.key(), p) for p in built]
                for total, _, p in sorted(built, key=lambda t: t[:2])[:KEEP_PER_STYLE]:
                    if budget is None or total <= budget:
                        add(p)
                continue
            for p in _first_built(req, b, sorted(scored), style, cache, KEEP_PER_STYLE):
                add(p)

    if pairs and 0 < req.veg_count < req.people:
        _add_pairs(req, pool, mixes, budget, cache, add)
    return list(plans.values())


FREE_DELIVERY_FROM = 499                    # app.pricing: a restaurant's items at or above this deliver free


def free_delivery_variants(req: MealRequest, b: Branch, plan: Plan) -> list[Plan]:
    """A plan just under ₹499 of items pays a delivery fee; one a little dearer can cost less in all because its
    delivery is free (Session 12 rule-breaker: Idli ×6 + Sambar ×3 = ₹585, Idli ×5 + Pongal + Sambar ×3 = ₹530).
    Variants: one plate swapped for a dearer main of the same kind and size (everyone is still fed exactly as
    before), or one more of a side already in the plan. Only worth trying when the plan costs more than the
    cheapest possible free-delivery bill (₹499 + 5% GST). The caller ranks everything by its real total."""
    bill = price(plan)
    if len(bill["branches"]) != 1 or bill["branches"][0]["delivery_fee"] == 0 or \
            bill["grand_total"] <= FREE_DELIVERY_FROM + round(FREE_DELIVERY_FROM * 0.05):
        return []
    main_ids = {i.item_id for i in b.mains}
    mains = [ln for ln in plan.lines if ln[1].item_id in main_ids]
    out = []
    for idx, (bb, it, q) in enumerate(mains):
        for alt in b.mains:
            if alt.item_id == it.item_id or kind(alt) != kind(it) or alt.serves != it.serves or \
                    alt.price <= it.price or not in_range(req, alt):
                continue
            swapped = merge(mains[:idx] + ([(bb, it, q - 1)] if q > 1 else []) + mains[idx + 1:] + [(bb, alt, 1)])
            if (lines := complete_meal(req, swapped, "value")) is not None:
                out.append(Plan(lines, "value"))
    for idx, (bb, it, q) in enumerate(plan.lines):
        if it.item_id not in main_ids and q < MAX_QTY:
            out.append(Plan(plan.lines[:idx] + [(bb, it, q + 1)] + plan.lines[idx + 1:], "value"))
    return [v for v in out if price(v)["grand_total"] < bill["grand_total"]]


def _first_built(req, b, ranked, style, cache, n) -> list[Plan]:
    """The first n mixes, best ranked first, that can actually be built here (a mix whose meal can't be completed,
    e.g. tiffin at a place with no sambar, is skipped instead of using up a place in the shortlist)."""
    out = []
    for _, _, mix in ranked:
        akey = ("asm", b.branch_id, style, tuple(mix.values()))
        if akey not in cache:
            cache[akey] = _assemble(req, [(b, mix)], style, cache)
        if (p := cache[akey]) is not None:
            out.append(p)
            if len(out) == n:
                break
    return out


def _add_pairs(req, pool, mixes, budget, cache, add):
    """Vegetarians' portions from one restaurant, the non-veg portions from another (the classic mixed order)."""
    most_nonveg = max(m["nonveg_mild"] + m["nonveg_spicy"] for m in mixes)
    for mix in [m for m in mixes if m["nonveg_mild"] + m["nonveg_spicy"] == most_nonveg]:
        veg = {k: (v if k.startswith("veg") else 0) for k, v in mix.items()}
        nonveg = {k: (v if k.startswith("nonveg") else 0) for k, v in mix.items()}
        if not sum(veg.values()) or not sum(nonveg.values()):
            continue
        for style in ("value", "variety"):
            def top(part):
                ranked = []
                for b in pool:
                    est = _estimate(req, b, part, style, cache)
                    if est is not None and (budget is None or est[0] <= budget):
                        ranked.append(((est[3], b.distance_km, b.branch_id), b))
                return [b for _, b in sorted(ranked, key=lambda x: x[0])[:PAIR_TOP]]
            for bv, bn in product(top(veg), top(nonveg)):
                if bv.restaurant_id != bn.restaurant_id:
                    add(_assemble(req, [(bv, veg), (bn, nonveg)], style, cache))
