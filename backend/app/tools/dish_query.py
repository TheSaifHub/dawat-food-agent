"""Understanding a dish request: "rendu kodi biryani karam kam under 300 in Madhapur" → dishes + filters (D-024).

Pure code, no database: it works on a DishIndex built from the dishes, dish_aliases and food_terms tables.
The order of the steps comes from the 4c probe (DECISIONS.md D-024), where each simpler approach matched
the wrong dish:
  1. the whole query is a known dish name or alias      → that dish ("ghee karam idli" keeps its "karam")
  2. take out price ("under 200", "300 ke andar") and area ("in Madhapur", "Madhapur lo")
  3. drop chat words ("bhai", "kavali", "something")    → never fuzzy-matched ("andar" scored 89 against
                                                           "anda" = egg)
  4. the rest is a known dish name or alias             → that dish ("2 pc chicken" keeps its 2);
     otherwise take out group size ("for 2 persons") and quantity ("rendu", "ek") and check again
  5. read diet and spice words, longest phrase first, with negations ("karam kam", "karam lekunda" = NOT
     spicy; word by word they read as "spicy", the opposite)
  6. fix typos word by word, only on clear evidence (score ≥ AUTO_MIN and no different word within LEAD);
     a borderline typo is returned for the user to confirm, never silently snapped
  7. match the remaining words: every word must appear in a name or alias of the dish (after translating
     kodi → chicken, chai → tea), or name its category ("biryani", "starters"). Never a whole-phrase fuzzy
     score: that matched "keema samosa" to the veg Aloo Samosa.
Diet words (veg, non veg, shakahari) are never matched against dish names; they become the is_veg filter,
so "veg thali" can't reach "Non-Veg Thali" through its words.
"""

import re
from collections import Counter
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

from app.text import compact, tokens
from app.tools.categories import CATEGORIES, CATEGORY_ALIASES, normalise_category

AUTO_MIN, CONFIRM_MIN, LEAD = 88, 80, 5     # per-word typo thresholds, from the probe (D-024)
QTY_MAX = 20

# Chat words: removed before matching and never typo-corrected. Each one was either seen scoring ≥ 80
# against a food word in the probe (want→walnut, cheap→chepa, accha→laccha, bhai→bhaji, akali→kali,
# friends→fried, nice→ice, andar→anda) or is ordinary Hinglish/Telugu/English request filler.
FILLER_PHRASES = ["do you have", "do u have", "can i get", "can i have", "i want", "i need", "i would like",
                  "give me", "get me", "send me", "is there", "are there", "kuch bhi", "ok na"]
FILLERS = {
    "i", "me", "my", "we", "us", "our", "you", "u", "your", "want", "wanna", "need", "like", "would", "get", "give",
    "send", "bring", "deliver", "order", "have", "has", "is", "are", "am", "be", "can", "could", "show", "find",
    "search", "suggest", "recommend", "please", "pls", "plz", "kindly", "bro", "bhai", "anna", "boss", "sir", "madam",
    "yaar", "ra", "hungry", "akali", "aakali", "akaliga", "something", "anything", "some", "any", "kuch", "kuchh",
    "koi", "emaina", "edaina", "edhaina", "yemaina", "food", "dish", "dishes", "item", "items", "khana", "khaana",
    "kavali", "kaavali", "kavalli", "kavalandi", "kaavalandi", "chahiye", "chaahiye", "chaiye", "chahie", "dedo",
    "dena", "dijiye", "bhejo", "bhej", "bhejdo", "ivvu", "ivvandi", "pampu", "pampandi", "tinali", "tinadaniki",
    "good", "best", "nice", "tasty", "yummy", "great", "cheap", "accha", "achha", "acha", "manchi", "mast", "today",
    "tonight", "now", "right", "quickly", "quick", "fast", "asap", "friends", "light", "available", "a", "an",
    "the", "to", "ko", "ka", "ki", "ke", "se", "hai", "h", "na", "kosam", "oka", "ok", "okay", "just", "only",
    "also", "too", "here", "there", "what", "which", "where", "near", "nearby", "around", "in", "at", "from", "lo",
    "mein", "me", "pe", "par", "andar", "under", "below", "price", "rate", "rs", "rupees", "inr", "budget",
}
# Words that help pick between forms ("chicken biryani FULL") but are not required to match: "half chicken
# biryani" must still find Chicken Dum Biryani, whose names never say "half".
SOFT = {"half", "full", "plate", "plates", "for", "with", "and", "of", "family", "pack", "persons", "person",
        "piece", "pieces", "pc", "pcs", "special", "hot", "fresh", "style", "combo", "regular", "large", "small",
        "medium", "big", "single", "double", "extra", "aadha"}
NEGATORS = {"kam", "less", "no", "not", "without", "ledu", "lekunda", "leni", "takkuva", "thakkuva", "nahi",
            "nahin", "bina", "low", "zero", "dont", "avoid", "తక్కువ", "లేకుండా", "లేదు"}
INTENSIFIERS = {"very", "extra", "more", "chala", "bahut", "bohot", "zyada", "jyada", "ekkuva", "too", "చాలా", "ఎక్కువ"}
SPICE_MEANS = {"spicy": ("min", 2), "very spicy": ("min", 3), "not spicy": ("max", 1)}
MODIFIER_KINDS = ("spice", "diet", "number", "portion")

PRICE_PATTERNS = [   # on normalised text: lower case, punctuation (₹, .) removed
    r"(?:under|below|within|upto|up to|less than|lessthan|max|maximum|budget|not more than)\s+"
    r"(?:of\s+)?(?:rs\s+|inr\s+)?(\d{2,5})(?:\s+(?:rs|rupees|inr|only|bucks))?",
    r"(?:rs\s+|inr\s+)?(\d{2,5})\s+(?:rs\s+|rupees\s+)?(?:lopu|lopala|lo pu|ke andar|ke under|tak|se kam|"
    r"or less|or below|and below|and under|max|maximum|లోపు|లోపల)",
    r"(?:rs|inr)\s+(\d{2,5})|(\d{2,5})\s+(?:rs|rupees|bucks)",
]
PEOPLE = re.compile(r"(?:\bfor\s+)?\b(\w+)\s+(?:people|persons|person|members|log|janta|mandiki|mandi ki)\b")
AREA_BEFORE = {"in", "near", "around", "nearby"}   # not "from"/"at": "biryani from Paradise" names a restaurant
AREA_AFTER = {"lo", "mein", "me", "లో"}


@dataclass
class Understood:
    """What the request was read as. Returned to the agent as JSON, so it can say what it understood."""
    words: list[str] = field(default_factory=list)          # dish words left after modifiers and fillers
    quantity: int | None = None
    people: int | None = None
    max_price: int | None = None
    area_text: str | None = None
    is_veg: bool | None = None
    min_spice: int | None = None
    max_spice: int | None = None
    corrections: dict[str, str] = field(default_factory=dict)
    unmatched_words: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_json(self) -> dict:
        out = {"dish_words": " ".join(self.words) or None, "quantity": self.quantity, "people": self.people,
               "max_price": self.max_price, "area_text": self.area_text, "is_veg": self.is_veg,
               "min_spice": self.min_spice, "max_spice": self.max_spice}
        if self.corrections:
            out["typo_corrections"] = self.corrections
        if self.unmatched_words:
            out["unmatched_words"] = self.unmatched_words
        if self.notes:
            out["notes"] = self.notes
        return out


@dataclass
class DishMatch:
    status: str                       # "exact" | "contains" | "category" | "any" | "confirm" | "none"
    tiers: dict[str, int]             # dish_id → tier (lower is better); empty for "any"/"confirm"/"none"
    understood: Understood
    confirm: dict | None = None       # {"word", "candidate", "score", "dishes"} for status "confirm"
    suggestions: list[str] = field(default_factory=list)


# Tiers, best first. The exact dish, then dishes whose NAME has every word, then one ALIAS, then the dish's
# names and aliases together ("keema samosa": "keema lukhmi" + "lukhmi samosa" → Mutton Lukhmi).
EXACT, NAME, ALIAS, ANY_FORM = 0, 2, 4, 6


class DishIndex:
    def __init__(self, dishes: list[dict], aliases: list[dict], terms: list[dict]):
        self.dishes = {d["dish_id"]: d for d in dishes}
        self.names = {d: r["name"] for d, r in self.dishes.items()}
        self.terms = {t["term_norm"]: (t["means"], t["kind"]) for t in terms}
        self.max_term_len = max((len(t.split()) for t in self.terms), default=1)
        self.translate = {k: v[0] for k, v in self.terms.items() if v[1] in ("ingredient", "dish word")}
        self.exact: dict[str, str] = {compact(tokens(r["name"])): d for d, r in self.dishes.items()}
        forms: dict[str, list[tuple[bool, list[str]]]] = {d: [(True, tokens(r["name"]))] for d, r in self.dishes.items()}
        for a in aliases:
            self.exact.setdefault(compact(a["alias_norm"].split()), a["dish_id"])
            forms[a["dish_id"]].append((False, a["alias_norm"].split()))
        # each form as a set of concepts: its own words plus their translations ("natu kodi" → country chicken)
        self.forms = {d: [(is_name, set(ws) | set(self._translate(ws))) for is_name, ws in fs] for d, fs in forms.items()}
        # dish_vocab: words that can name food. vocab adds the lexicon's other words (spicy, veg, rendu), as
        # typo-correction targets only.
        self.dish_vocab = {w for fs in self.forms.values() for _, s in fs for w in s}
        self.dish_vocab |= {w for t in self.translate for w in t.split()}
        self.dish_vocab |= set(CATEGORIES) | set(CATEGORY_ALIASES)              # "starters", "sweets", "drinks"
        self.vocab_list = sorted(w for w in self.dish_vocab | {w for t in self.terms for w in t.split()}
                                 if not w.isdigit())
        self.diet_words = {t for t, (_, kind) in self.terms.items() if kind == "diet" and " " not in t}
        self.freq = Counter(w for fs in self.forms.values() for w in set().union(*(c for _, c in fs)))

    # ── helpers ──
    def _translate(self, words: list[str]) -> list[str]:
        """Longest-first lexicon translation of ingredient/dish words: kodi → chicken, chepala → fish."""
        out, i = [], 0
        while i < len(words):
            for n in range(min(self.max_term_len, len(words) - i), 0, -1):
                phrase = " ".join(words[i:i + n])
                if phrase in self.translate:
                    out += self.translate[phrase].split()
                    i += n
                    break
            else:
                out.append(words[i])
                i += 1
        return out

    def meaning(self, w: str) -> str:
        return self.terms[w][0] if w in self.terms else w

    def kind(self, w: str) -> str | None:
        return self.terms[w][1] if w in self.terms else None

    def exact_dish(self, words: list[str]) -> str | None:
        return self.exact.get(compact(words)) if words else None

    def correct(self, w: str) -> tuple[str, str | None, float]:
        """("auto"|"confirm"|"none", candidate, score) for an unknown word. Auto only when the best word scores
        ≥ AUTO_MIN and no word meaning something else is within LEAD points (tika: tikka 89 vs tikha 89, which
        means "spicy" → confirm). For a confirm, the candidate offered is the best FOOD word."""
        if len(w) < 4 or w.isdigit():
            return "none", None, 0
        top = process.extract(w, self.vocab_list, scorer=fuzz.ratio, limit=6)
        if not top or top[0][1] < CONFIRM_MIN:
            return "none", None, top[0][1] if top else 0
        score = top[0][1]
        # among equally close spellings, the one more dishes use ("burgr": burger, not the rarer "burgar")
        best = max((c for c, s, _ in top if s == score), key=lambda c: (self.freq.get(c, 0), c))
        rivals = [c for c, s, _ in top if c != best and score - s < LEAD and not self._same(best, c)]
        if score >= AUTO_MIN and not rivals:
            return "auto", best, score
        # "vegg": veg and egg tie. Reading it as vegetarian can only narrow the results; offering "egg" to
        # someone who may be vegetarian is the one mistake this search must never make.
        close = [c for c, s, _ in top if score - s < LEAD]
        if rivals and (veg := next((c for c in close if self.meaning(c) == "vegetarian"), None)):
            return "auto", veg, score
        food = next(((c, s) for c, s, _ in top if s >= CONFIRM_MIN and c in self.dish_vocab), (best, score))
        return "confirm", food[0], food[1]

    def _same(self, a: str, b: str) -> bool:
        """One choice if they mean the same, share a 4-letter stem (spicy/spice), or are spellings of each other
        and neither is a diet/spice/number word (shawarma/shawerma yes; tikka/tikha no)."""
        if self.meaning(a) == self.meaning(b) or (len(a) >= 4 and a[:4] == b[:4]):
            return True
        return (self.kind(a) not in MODIFIER_KINDS and self.kind(b) not in MODIFIER_KINDS
                and fuzz.ratio(a, b) >= 80)

    def singular(self, w: str) -> str:
        """'biryanis' → 'biryani'. Category words are kept as typed: "sweets" means desserts, not "sweet"."""
        if w in self.dish_vocab or normalise_category(w):
            return w
        if len(w) > 3 and w.endswith("s") and w[:-1] in self.dish_vocab:
            return w[:-1]
        return w

    # ── matching the dish words ──
    def match_words(self, words: list[str]) -> dict[str, int]:
        """dish_id → tier (EXACT, NAME, ALIAS, ANY_FORM; one less when the soft words also match).
        A category word is satisfied by the dish's category: "biryani" by every dish in the biryani category."""
        tiers: dict[str, int] = {}
        if (d := self.exact_dish(words)) or (d := self.exact_dish(self._translate(words))):
            tiers[d] = EXACT
        required = [w for w in self._translate(words) if w not in SOFT and w not in self.diet_words]
        soft = [w for w in words if w in SOFT]
        if not required:
            return tiers
        cats = {w: normalise_category(w) for w in required}
        for d, fs in self.forms.items():
            if d in tiers:
                continue
            cat = self.dishes[d]["category"]
            name_c = fs[0][1]
            # a category word counts only through the dish's category or its NAME: "biryani" must not pull in
            # Bagara Rice through its alias "biryani rice"
            ok = lambda concepts: all((cats[w] == cat or w in name_c) if cats[w] else w in concepts for w in required)
            tier = (NAME if any(ok(c) for is_name, c in fs if is_name) else
                    ALIAS if any(ok(c) for _, c in fs) else
                    ANY_FORM if ok(set().union(*(c for _, c in fs))) else None)
            if tier is not None:
                has_soft = bool(soft) and any(all(s in c for s in soft) for _, c in fs)
                tiers[d] = tier - (1 if has_soft else 0)
        return tiers

    def suggest(self, words: list[str], limit: int = 3) -> list[str]:
        """Dishes sharing the most words with an unmatched request, for the agent to offer."""
        req = [w for w in self._translate(words) if w not in SOFT and w not in self.diet_words]
        scored = []
        for d, fs in self.forms.items():
            allc = set().union(*(c for _, c in fs))
            hits = sum(w in allc for w in req)
            if hits:
                scored.append((-hits, self.names[d]))
        return [n for _, n in sorted(scored)[:limit]]


def _take_price(text: str, u: Understood) -> str:
    for p in PRICE_PATTERNS:
        if m := re.search(p, text):
            u.max_price = int(next(g for g in m.groups() if g))
            return (text[:m.start()] + " " + text[m.end():]).strip()
    return text


def _take_people(text: str, idx: DishIndex, u: Understood) -> str:
    """'for 2 persons', 'naalugu mandiki' → people (for plan_meal), not a quantity."""
    m = PEOPLE.search(text)
    if m:
        w = m.group(1)
        n = int(w) if w.isdigit() else int(idx.meaning(w)) if idx.kind(w) == "number" else None
        if n:
            u.people = n
            u.notes.append(f"a group of {n}: for portions and budgets use plan_meal")
            return (text[:m.start()] + " " + text[m.end():]).strip()
    return text


def _take_quantity(words: list[str], idx: DishIndex, u: Understood) -> list[str]:
    """A number word or small number next to the dish: "ek mutton biryani", "rendu kodi biryani", "idli 2".
    Not "65" in "chicken 65" (part of the name) and not "do" in "do you have" (a filler phrase)."""
    out = []
    for i, w in enumerate(words):
        is_word = idx.kind(w) == "number"
        is_num = is_word or (w.isdigit() and 1 <= int(w) <= QTY_MAX)
        before_food = i + 1 < len(words) and words[i + 1] not in FILLERS
        after_food = i == len(words) - 1 and i > 0 and w.isdigit()
        if is_num and u.quantity is None and (before_food or after_food):
            # a digit that, with the words next to it, spells a dish name stays in it ("2 pc chicken karam kam")
            in_name = any(idx.exact_dish(words[s:e]) for s in range(max(0, i - 3), i + 1)
                          for e in range(i + 1, min(len(words), i + 4) + 1) if e - s >= 2)
            if is_word or not in_name:
                u.quantity = int(idx.meaning(w)) if is_word else int(w)
                continue
        out.append(w)
    return out


def _take_modifiers(words: list[str], idx: DishIndex, u: Understood) -> list[str]:
    """Diet and spice words, longest phrase first, then negations/intensifiers around a single spice word."""
    out, spice, diet, used, i = [], [], [], set(), 0
    while i < len(words):
        for n in range(min(idx.max_term_len, len(words) - i), 0, -1):
            phrase = " ".join(words[i:i + n])
            means, kind = idx.terms.get(phrase, (None, None))
            if kind in ("spice", "diet"):
                if kind == "spice" and n == 1 and means == "spicy":
                    near = set(words[max(0, i - 2):i] + words[i + 1:i + 3])
                    if NEGATORS & near:
                        means, used = "not spicy", used | (NEGATORS & near)
                    elif INTENSIFIERS & set(words[max(0, i - 2):i + 2]):
                        means, used = "very spicy", used | (INTENSIFIERS & near)
                (spice if kind == "spice" else diet).append(means)
                i += n
                break
        else:
            out.append(words[i])
            i += 1
    out = [w for w in out if w not in used]
    if len(set(spice)) > 1:
        u.notes.append(f"conflicting spice words {sorted(set(spice))}: no spice filter applied; ask the user")
    elif spice:
        bound, level = SPICE_MEANS[spice[0]]
        if bound == "min":
            u.min_spice = level
        else:
            u.max_spice = level
    vegs = {d in ("vegetarian", "no egg") for d in diet}
    if len(vegs) > 1:
        u.notes.append("both veg and non-veg asked for: no diet filter applied; for a mixed group use plan_meal")
    elif vegs:
        u.is_veg = vegs.pop()
    return out


def find_area_text(words: list[str], area_score, food_words: set[str]) -> tuple[list[str], str | None]:
    """'… in Madhapur', 'near KPHB', 'Madhapur lo …'. `area_score(text)` is 2 when the text resolves to an
    area (or a verified out-of-coverage place), else 0. Prefers the longest text that resolves; otherwise,
    after "in"/"near", takes the run of non-food words as an area we don't know, so the search stops and
    asks instead of searching everywhere. Returns (remaining words, area text or None)."""
    spans = []                                                    # (start, end, index of in/near/lo)
    for i, w in enumerate(words):
        if w in AREA_BEFORE:
            spans += [(i + 1, i + 1 + n, i) for n in (3, 2, 1) if i + 1 + n <= len(words)]
        elif w in AREA_AFTER and i > 0:
            spans += [(i - n, i, i) for n in (3, 2, 1) if i - n >= 0]
    for s, e, p in spans:
        if area_score(" ".join(words[s:e])) == 2:
            return [w for k, w in enumerate(words) if not (s <= k < e or k == p)], " ".join(words[s:e])
    for i, w in enumerate(words):
        if w in AREA_BEFORE:
            run = []
            for x in words[i + 1:]:
                if x in food_words or x in FILLERS:
                    break
                run.append(x)
            if run:
                return words[:i] + words[i + 1 + len(run):], " ".join(run)
    return words, None


def understand(query: str, idx: DishIndex, area_score) -> DishMatch:
    u = Understood()
    raw = tokens(query.replace("₹", " rs "))
    if d := idx.exact_dish(raw):                                       # step 1
        u.is_veg = _diet_only(raw, idx)
        u.words = raw
        return DishMatch("exact", {**idx.match_words(raw), d: EXACT}, u)

    text = _take_price(" ".join(raw), u)                               # step 2: price and area
    words, u.area_text = find_area_text(text.split(), area_score, idx.dish_vocab)
    joined = f" {' '.join(words)} "
    for p in FILLER_PHRASES:                                           # step 3 (phrases first: "do you have")
        joined = joined.replace(f" {p} ", " ")
    words = [w for w in joined.split() if w not in FILLERS or w in SOFT]

    # step 4: a dish name or alias, checked BEFORE group size and quantity are read, so the numbers inside
    # names stay there ("2 pc chicken please"; "chicken biryani 2 persons" is the Full plate). Found by a
    # planted bug, D-024.
    if not (d := idx.exact_dish(words)):
        words = _take_quantity(_take_people(" ".join(words), idx, u).split(), idx, u)
        d = idx.exact_dish(words)
    if d:
        u.is_veg, u.words = _diet_only(words, idx), words              # its own words stay part of the name
        return DishMatch("exact", {**idx.match_words(words), d: EXACT}, u)

    words = _take_modifiers(words, idx, u)                             # step 5
    leftovers = [w for w in words if w not in SOFT and (w in NEGATORS or w in INTENSIFIERS or
                                                        idx.kind(w) in ("number", "spice", "diet"))]
    if leftovers:                                                      # "biryani bhej do", "kam" on its own
        u.notes.append(f"ignored {leftovers}")
        words = [w for w in words if w not in leftovers]

    fixed, pending = [], None                                          # step 6
    for w in map(idx.singular, words):
        if w in idx.dish_vocab or w.isdigit():
            fixed.append(w)
            continue
        verdict, cand, score = idx.correct(w)
        if verdict == "auto":
            u.corrections[w] = idx.meaning(cand)
            fixed.append(cand)
        else:
            if verdict == "confirm" and pending is None:
                pending = (w, cand, score)
            fixed.append(w)
    if any(idx.kind(w) in ("spice", "diet") for w in fixed):         # a typo fixed into "spicy" or "veg"
        fixed = _take_modifiers(fixed, idx, u)
    u.words = fixed
    if not fixed:
        return DishMatch("any", {}, u)

    known = [w for w in fixed if w in idx.dish_vocab or w.isdigit()]
    unknown = [w for w in fixed if w not in known]
    if not unknown and (tiers := idx.match_words(fixed)):             # step 7
        return DishMatch(_kind(tiers, idx, fixed), tiers, u)
    if pending:                                                        # a borderline typo: ask, don't snap
        w, cand, score = pending
        if trial := idx.match_words([cand if x == w else x for x in fixed]):
            names = [idx.names[d] for d, _ in sorted(trial.items(), key=lambda kv: (kv[1], idx.names[kv[0]]))[:5]]
            return DishMatch("confirm", {}, u, confirm={"word": w, "candidate": idx.meaning(cand),
                                                        "score": round(score), "dishes": names})
    u.unmatched_words = unknown
    if unknown and known and (tiers := idx.match_words(known)):       # match what we can; say what we couldn't
        return DishMatch(_kind(tiers, idx, known), tiers, u)
    return DishMatch("none", {}, u, suggestions=idx.suggest(known or fixed))


def _diet_only(words: list[str], idx: DishIndex) -> bool | None:
    u = Understood()
    _take_modifiers(list(words), idx, u)
    return u.is_veg


def _kind(tiers: dict[str, int], idx: DishIndex, words: list[str]) -> str:
    if EXACT in tiers.values():
        return "exact"
    req = [w for w in idx._translate(words) if w not in SOFT and w not in idx.diet_words]
    return "category" if req and all(normalise_category(w) for w in req) else "contains"
