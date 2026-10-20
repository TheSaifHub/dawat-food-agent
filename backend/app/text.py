"""Text normalisation shared by every search tool (D-023).

`norm_alias` must stay IDENTICAL to data_pipeline/check_menu_templates.py:norm_alias, because the
database's alias_norm columns were produced with it; tests/test_text.py compares the two on real data.
"""

import re
import unicodedata

_APOSTROPHES = "'’‘`´"


def norm_alias(s: str) -> str:
    # Keep Telugu combining marks (category M*), which [^\w\s] would strip.
    s = unicodedata.normalize("NFKC", s).lower().replace("&", " and ")
    s = "".join(c if (c.isalnum() or c.isspace() or unicodedata.category(c).startswith("M") or c in "‌‍")
                else " " for c in s)
    return re.sub(r"\s+", " ", s).strip()


def tokens(s: str) -> list[str]:
    """Words of a name or query. Apostrophes are dropped first, so "Domino's" → ["dominos"], not ["domino", "s"]."""
    s = unicodedata.normalize("NFKC", s)
    for a in _APOSTROPHES:
        s = s.replace(a, "")
    return norm_alias(s).split()


def compact(words: list[str] | str) -> str:
    """Spaces removed: "mc donalds", "McDonald's" and "mcdonalds" all become "mcdonalds"."""
    return "".join(tokens(words) if isinstance(words, str) else words)
