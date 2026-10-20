"""Correct near-miss restaurant names in a reply before the user sees it (Saif, Session 16, D-041; failure F-3).

    correct_names(reply, tool_results) → (reply, [[as_written, exact_name], ...])

Flash-Lite sometimes writes "Annapura" for "Annapurna" although the tool said "Annapurna". The prompt already says to
keep names exactly; this is the code-side net. Only RESTAURANT names from this conversation's tool results are used,
and a stretch of the reply is replaced only if:
  · it has the same number of words as the name, starts with a capital letter, and isn't glued to a digit or
    letter ("Annapura2"), so numbers are never touched;
  · it is close (rapidfuzz ratio ≥ 85) but not already exactly the name, ignoring case;
  · no other known restaurant name matches it as well or better (two similar names are left alone).
Everything else, including dish names and any text in other scripts, is left as written.
"""

import re

from rapidfuzz import fuzz

THRESHOLD = 85
MIN_LEN = 5
_WORD = re.compile(r"[A-Za-z][A-Za-z'’&.-]*")


def restaurant_names(value, out: set) -> set:
    """Every restaurant name inside a tool result: "restaurant": "Name" or "restaurant": {"name": "Name"}."""
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


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", s.lower().replace("’", "'").replace("'", ""))


def correct_names(reply: str, tool_results: list) -> tuple[str, list[list[str]]]:
    names = sorted({n for n in restaurant_names(tool_results, set()) if len(_norm(n)) >= MIN_LEN}, key=len, reverse=True)
    if not names or not reply:
        return reply, []
    words = list(_WORD.finditer(reply))
    replacements: list[tuple[int, int, str, str]] = []           # (start, end, written, exact)
    taken: set[int] = set()
    for name in names:
        k = len(name.split())
        for i in range(len(words) - k + 1):
            span = words[i:i + k]
            idx = set(range(i, i + k))
            if idx & taken:
                continue
            start, end = span[0].start(), span[-1].end()
            written = reply[start:end].rstrip(".")
            end = start + len(written)
            if not written[:1].isupper():
                continue
            if (start and reply[start - 1].isalnum()) or (end < len(reply) and reply[end].isalnum()):
                continue                                           # glued to a digit or letter ("Annapura2"): leave it
            a, b = _norm(written), _norm(name)
            if a == b:
                taken |= idx                                       # already exact: protect it from other names
                continue
            score = fuzz.ratio(a, b)
            if score < THRESHOLD:
                continue
            if any(fuzz.ratio(a, _norm(other)) >= score for other in names if other != name):
                continue                                           # another known name fits as well: leave it
            replacements.append((start, end, written, name))
            taken |= idx
    if not replacements:
        return reply, []
    out, last, fixes = [], 0, []
    for start, end, written, exact in sorted(replacements):
        out.append(reply[last:start] + exact)
        last = end
        fixes.append([written, exact])
    out.append(reply[last:])
    return "".join(out), fixes
