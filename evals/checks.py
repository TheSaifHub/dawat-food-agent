"""Automatic checks on one Dawat AI turn (Phase 6f, D-038). Pure functions: a reply, the tool results the model saw,
and the user's words in → a list of {check, ok, detail}. The runner (run_evals.py) and Phase 10 use them.

Always run:
  numbers_grounded   every number ≥ 20 in the reply appears in a tool result of this conversation or in the user's
                     own words. Catches invented prices and totals, including ones not written as "₹N" (D-034).
  names_spelled      a restaurant name from the tool results that the reply almost writes (fuzzy ≥ 85) but never
                     writes exactly is flagged ("Annapura" for "Annapurna", D-037). It may over-flag; each flag
                     names both spellings so a person can judge.
  diet_notes_copied  when plan_meal answered ok this turn, every plan's diet_note appears in the reply (D-036).
  no_failure_reply   the turn ended ok (not busy / step_cap).
Per-turn expectations (from the case file): script, english, tools, no_tools, args, statuses, reply_has_any,
reply_has_none, min_calls, no_numbers, orders, result_keys, cart_nonveg, cart_lines_min.
"""

import json
import re

from rapidfuzz import fuzz

NOT_ENGLISH = {"hai", "mein", "milega", "bhai", "kya", "unnai", "undi", "kaavali", "chala", "andi", "haan", "nahi",
               "aap", "lope", "manchi", "kuch", "yeh", "inmein", "karna", "bataiye", "ikkada", "kavala", "dorikey"}
NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")


def script_of(text: str) -> str:
    if any("ऀ" <= c <= "ॿ" for c in text):
        return "devanagari"
    if any("ఀ" <= c <= "౿" for c in text):
        return "telugu"
    return "latin"


def numbers_in(value, out: set) -> set:
    """Every number inside a JSON value: numbers, and digits inside strings (ids are harmless extras)."""
    if isinstance(value, dict):
        for v in value.values():
            numbers_in(v, out)
    elif isinstance(value, list):
        for v in value:
            numbers_in(v, out)
    elif isinstance(value, bool):
        pass
    elif isinstance(value, (int, float)):
        out.add(float(value))
    elif isinstance(value, str):
        out.update(float(x.replace(",", "")) for x in NUMBER.findall(value))
    return out


def restaurant_names(value, out: set) -> set:
    if isinstance(value, dict):
        for k, v in value.items():
            if k == "restaurant" and isinstance(v, str):
                out.add(v)
            elif k == "restaurant" and isinstance(v, dict) and isinstance(v.get("name"), str):
                out.add(v["name"])
            else:
                restaurant_names(v, out)
    elif isinstance(value, list):
        for v in value:
            restaurant_names(v, out)
    return out


def _c(name: str, ok: bool, detail="") -> dict:
    return {"check": name, "ok": bool(ok), "detail": detail}


def numbers_grounded(reply: str, tool_results: list, user_words: list[str]) -> dict:
    known = numbers_in(tool_results, set()) | numbers_in(user_words, set())
    said = {float(x.replace(",", "")) for x in NUMBER.findall(reply)}
    unknown = sorted(n for n in said if n >= 20 and n not in known)
    return _c("numbers_grounded", not unknown, f"not from any tool result: {unknown}" if unknown else "")


def names_spelled(reply: str, tool_results: list) -> dict:
    low = reply.lower()
    flags = []
    for name in sorted(restaurant_names(tool_results, set())):
        n = name.lower()
        if len(n) >= 5 and n not in low and fuzz.partial_ratio(n, low) >= 85:
            window = max((low[i:i + len(n)] for i in range(max(1, len(low) - len(n) + 1))),
                         key=lambda w: fuzz.ratio(n, w))
            flags.append(f"{name!r} written as {window!r}")
    return _c("names_spelled", not flags, "; ".join(flags))


def diet_notes_copied(reply: str, plan_results: list[dict]) -> dict | None:
    notes = [p["diet_note"] for r in plan_results if r.get("status") == "ok" for p in r.get("plans", [])]
    if not notes:
        return None
    squash = lambda s: re.sub(r"\s+", " ", s.replace("*", "")).strip().lower()  # noqa: E731
    missing = [n for n in notes if squash(n) not in squash(reply)]
    return _c("diet_notes_copied", not missing, f"missing: {missing}" if missing else "")


def expectations(expect: dict, reply: str, calls: list[dict], orders_placed: int, results: list | None = None,
                 cart_nonveg: int | None = None, cart_lines: int | None = None) -> list[dict]:
    """calls: [{"tool", "arguments", "status"}] for this turn; results: their tool results, in the same order."""
    out = []
    names = [c["tool"] for c in calls]
    if "script" in expect:
        out.append(_c("script", script_of(reply) == expect["script"], f"got {script_of(reply)}"))
    if expect.get("english"):
        hits = sorted(set(re.findall(r"[a-z]+", reply.lower())) & NOT_ENGLISH)
        out.append(_c("english_only", not hits, f"non-English words: {hits}" if hits else ""))
    for t in expect.get("tools", []):
        out.append(_c(f"called {t}", t in names, f"called: {names}"))
    for t in expect.get("no_tools", []):
        out.append(_c(f"did not call {t}", t not in names, f"called: {names}"))
    for t, want in expect.get("args", {}).items():
        got = next((c["arguments"] for c in calls if c["tool"] == t), None)
        bad = {k: (got or {}).get(k) for k, v in want.items() if (got or {}).get(k) != v}
        out.append(_c(f"{t} arguments", got is not None and not bad, f"got {got}" if bad or got is None else ""))
    for t, want in expect.get("statuses", {}).items():
        got = [c["status"] for c in calls if c["tool"] == t]
        out.append(_c(f"{t} status {want}", want in got, f"got {got}"))
    if "reply_has_any" in expect:
        words = [w for w in expect["reply_has_any"] if w.lower() in reply.lower()]
        out.append(_c("reply mentions", bool(words), f"none of {expect['reply_has_any']}"))
    if "reply_has_none" in expect:
        words = [w for w in expect["reply_has_none"] if w.lower() in reply.lower()]
        out.append(_c("reply avoids", not words, f"said {words}" if words else ""))
    for t, n in expect.get("min_calls", {}).items():
        out.append(_c(f"{t} called ≥ {n}×", names.count(t) >= n, f"called {names.count(t)}×"))
    if expect.get("no_numbers"):
        nums = [x for x in NUMBER.findall(reply) if float(x.replace(",", "")) >= 20]
        out.append(_c("no prices yet", not nums, f"numbers: {nums}" if nums else ""))
    for t, keys in expect.get("result_keys", {}).items():
        got = [r for c, r in zip(calls, results or []) if c["tool"] == t]
        missing = [k for k in keys if not any(isinstance(r, dict) and k in r for r in got)]
        out.append(_c(f"{t} result has {keys}", bool(got) and not missing, f"missing {missing}" if missing else ""))
    if "cart_nonveg" in expect:
        out.append(_c(f"non-veg items in cart = {expect['cart_nonveg']}", cart_nonveg == expect["cart_nonveg"],
                      f"found {cart_nonveg}"))
    if "cart_lines_min" in expect:
        out.append(_c(f"cart still has ≥ {expect['cart_lines_min']} line(s)", (cart_lines or 0) >= expect["cart_lines_min"],
                      f"cart has {cart_lines}"))
    if "orders" in expect:
        out.append(_c(f"orders placed = {expect['orders']}", orders_placed == expect["orders"], f"placed {orders_placed}"))
    return out


def check_turn(*, reply: str, status: str, calls: list[dict], tool_results_so_far: list, this_turn_results: list,
               user_words: list[str], expect: dict, orders_placed: int, cart_nonveg: int | None = None,
               cart_lines: int | None = None) -> list[dict]:
    plan_results = [r for c, r in zip(calls, this_turn_results) if c["tool"] == "plan_meal"]
    out = [numbers_grounded(reply, tool_results_so_far, user_words), names_spelled(reply, tool_results_so_far),
           _c("no_failure_reply", status == "ok", f"status {status}")]
    if (d := diet_notes_copied(reply, plan_results)) is not None:
        out.append(d)
    return out + expectations(expect, reply, calls, orders_placed, this_turn_results, cart_nonveg, cart_lines)


def parse_tool_message(content: str):
    try:
        return json.loads(content)
    except (TypeError, json.JSONDecodeError):
        return {}
