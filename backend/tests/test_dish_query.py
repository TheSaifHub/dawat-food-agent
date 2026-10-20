"""Understanding dish requests (D-024): app/tools/dish_query.py on the real dish index (dishes, dish_aliases,
food_terms as seeded). Each "probe" test below is a query that matched the WRONG dish in the 4c probe before
the fix it names."""

import pytest

from app.tools.areas import resolve_area
from app.tools.dish_query import EXACT, FILLERS, SOFT, understand
from app.tools.reference import get_reference


@pytest.fixture(scope="module")
def ref(db_conn):
    return get_reference(db_conn)


@pytest.fixture(scope="module")
def idx(ref):
    return ref.dish_index


@pytest.fixture(scope="module")
def u(ref, idx):
    def area_score(text):
        return 2 if resolve_area(ref, text)["status"] in ("ok", "confirm_area", "outside_coverage") else 0

    def run(q):
        return understand(q, idx, area_score)
    return run


def best(m, idx):
    """The dish names in tier order (then name)."""
    return [idx.names[d] for d, _ in sorted(m.tiers.items(), key=lambda kv: (kv[1], idx.names[kv[0]]))]


def veg_of(m, idx):
    return {idx.dishes[d]["is_veg"] for d in m.tiers}


# ── Saif's nine ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("q, top, qty", [("ek mutton biryani", "Mutton Dum Biryani", 1),
                                         ("rendu kodi biryani", "Chicken Dum Biryani", 2)])
def test_quantity_words_are_taken_out_and_the_dish_is_exact(u, idx, q, top, qty):
    m = u(q)
    assert m.status == "exact" and best(m, idx)[0] == top and m.understood.quantity == qty


@pytest.mark.parametrize("q", ["karam kam", "karam lekunda", "spicy kam", "kam spicy", "less karam", "karam ledu",
                               "not spicy", "teekha nahi", "no spice", "కారం లేకుండా", "thakkuva karam"])
def test_not_spicy_phrasings_mean_max_spice_1_never_spicy(u, q):
    """Probe: word by word, "karam kam" and "karam lekunda" read as SPICY (the opposite); as one fuzzy
    phrase, "karam kam" matched Ghee Karam Idli and "karam lekunda" matched Dal Tadka."""
    m = u(q)
    assert m.understood.max_spice == 1 and m.understood.min_spice is None
    assert m.status == "any", f"{q!r} matched a dish: {m.tiers}"


@pytest.mark.parametrize("q", ["బిర్యానీ", "biriyani", "biryani", "briyani", "biryanis"])
def test_a_bare_biryani_word_is_the_whole_category_not_one_dish(u, idx, q):
    """Probe: whole-phrase fuzzy matching turned "biriyani" and "బిర్యానీ" into Chicken Dum Biryani only."""
    m = u(q)
    assert m.status == "category"
    cats = {idx.dishes[d]["category"] for d in m.tiers}
    assert cats == {"biryani"} and len(m.tiers) >= 10


def test_chiken_65_is_chicken_65(u, idx):
    m = u("chiken 65")
    assert best(m, idx)[0] == "Chicken 65" and m.understood.quantity is None   # 65 is the name, not a count


@pytest.mark.parametrize("q, top", [("2 pc chicken please", "Crispy Fried Chicken (2 pcs)"),
                                    ("2 pc chicken karam kam", "Crispy Fried Chicken (2 pcs)"),
                                    ("gulab jamun 2 pcs under 100", "Gulab Jamun (2 pcs)"),
                                    ("bhai chicken biryani 2 persons", "Chicken Dum Biryani (Full)")])
def test_a_small_number_inside_a_dish_name_is_not_a_quantity(u, idx, q, top):
    """Found by a planted bug (D-024): 18 names/aliases contain 1–20 ("2 pc chicken"). With extra words around
    them, the number must stay part of the name."""
    m = u(q)
    assert best(m, idx)[0] == top and m.understood.quantity is None


def test_paneer_under_200(u, idx):
    """Probe: as one phrase it matched "Paneer 65" (86) and "pani" = water (77)."""
    m = u("paneer under 200")
    assert m.understood.max_price == 200 and m.status == "contains"
    # every match says paneer in its name, or in an alias (Cottage Cheese Steak: "paneer steak")
    assert all("paneer" in idx.names[d].lower() or t > 2 for d, t in m.tiers.items()) and len(m.tiers) >= 10
    assert veg_of(m, idx) == {True}


def test_something_veg_not_spicy_in_madhapur(u):
    """Probe: as one phrase it matched Veg Dum Biryani; word by word, "not spicy" read as "spicy"."""
    m = u("something veg not spicy in Madhapur")
    j = m.understood
    assert m.status == "any" and j.is_veg is True and j.max_spice == 1 and j.area_text == "madhapur"
    assert j.words == [] and not j.unmatched_words


# ── other probe failures, each now a regression test ─────────────────────
def test_veg_thali_never_matches_non_veg_through_its_words(u, idx):
    """Probe: "veg thali" ⊂ "non veg thali" (an alias of Andhra Non-Veg Meals) by words. Diet words are now a
    filter (is_veg=True), and search_dishes drops the non-veg dish; the exact dish is veg."""
    m = u("veg thali")
    assert m.understood.is_veg is True
    exact = [d for d, t in m.tiers.items() if t == EXACT]
    assert all(idx.dishes[d]["is_veg"] for d in exact)
    assert u("non veg thali").understood.is_veg is False


def test_ghee_karam_idli_keeps_its_karam(u, idx):
    m = u("ghee karam idli")
    assert best(m, idx)[0] == "Ghee Karam Idli" and m.understood.min_spice is None and m.understood.max_spice is None


def test_keema_samosa_is_the_mutton_lukhmi_not_aloo_samosa(u, idx):
    """Probe: WRatio matched "keema samosa" to the veg Samosa (90): a meat request answered with the wrong dish."""
    m = u("keema samosa")
    assert best(m, idx) == ["Mutton Lukhmi"] and veg_of(m, idx) == {False}


def test_panir_is_paneer_not_pani(u, idx):
    """Probe: "panir" scored 89 against "pani" (water). Fixed by adding panir to food_lexicon.csv."""
    m = u("panir tikka")
    assert best(m, idx)[0] == "Paneer Tikka"


def test_andar_is_not_anda(u, idx):
    """Probe: "andar" (inside) scored 89 against "anda" (egg): "300 ke andar" must be a price, not egg."""
    m = u("biryani 300 ke andar")
    assert m.understood.max_price == 300 and m.status == "category" and "Egg Biryani" in best(m, idx)
    assert not m.understood.corrections
    m = u("andar biryani")
    assert "anda" not in m.understood.words and not m.understood.corrections


def test_sweets_means_desserts_not_sweet_corn_soup(u, idx):
    m = u("sweets")
    assert m.status == "category" and {idx.dishes[d]["category"] for d in m.tiers} == {"dessert"}


@pytest.mark.parametrize("q, cat", [("starters", "starter"), ("veg starters", "starter"), ("drinks under 100", "drink"),
                                    ("desserts", "dessert"), ("pizza", "pizza"), ("mandi", "mandi")])
def test_category_words(u, idx, q, cat):
    """The category, plus dishes whose NAME has the word ("Mandi Rice (Plain)" is a rice dish), never one that
    only has it in an alias."""
    m = u(q)
    assert m.status == "category" and m.tiers
    word = q.split()[-1] if "under" not in q else q.split()[0]
    for d in m.tiers:
        assert idx.dishes[d]["category"] == cat or word in idx.names[d].lower(), idx.names[d]


def test_for_2_persons_is_a_group_not_a_quantity(u):
    m = u("mutton biryani for 2 persons")
    assert m.understood.people == 2 and m.understood.quantity is None and m.status == "exact"


def test_do_you_have_is_not_the_number_two(u):
    m = u("do you have biryani")
    assert m.understood.quantity is None and m.status == "category"
    assert u("do idli").understood.quantity == 2


def test_vegg_is_read_as_veg_never_egg(u, idx):
    """Found while checking typos: "vegg" ties veg and egg (86). Offering "egg biryani" to someone who may be
    vegetarian is the one mistake this must never make, so a tie with the veg word reads as veg."""
    m = u("vegg biryani")
    assert m.understood.is_veg is True and "egg" not in m.understood.words


@pytest.mark.parametrize("q, word, cand", [("muttun biryani", "muttun", "mutton"), ("noodels", "noodels", "noodles"),
                                           ("tika", "tika", "tikka")])
def test_borderline_typos_ask_instead_of_snapping(u, q, word, cand):
    """Like areas (D-023): 80–87, or a tie with a word meaning something else (tika: tikka vs tikha = spicy)."""
    m = u(q)
    assert m.status == "confirm" and m.confirm["word"] == word and m.confirm["candidate"] == cand and not m.tiers


@pytest.mark.parametrize("q, fixed, top", [("biryni", "biryani", None), ("burgr", "burger", None),
                                           ("shawrma", "shawarma", "Chicken Shawarma Roll"),
                                           ("tandori chicken", "tandoori", "Tandoori Chicken (Half)"),
                                           ("spicey chicken", "spicy", None), ("kheema", "keema", "Mutton Lukhmi")])
def test_clear_typos_are_corrected_and_reported(u, idx, q, fixed, top):
    m = u(q)
    assert fixed in m.understood.corrections.values()
    if top:
        assert best(m, idx)[0] == top
    if fixed == "burger":
        assert len(m.tiers) >= 5            # every burger, not just the two whose alias says "burgar"


def test_unknown_food_word_is_reported_not_hidden(u):
    m = u("pork biryani")
    assert m.understood.unmatched_words == ["pork"]


def test_unknown_request_gives_no_dish(u):
    m = u("xqzt")
    assert m.status == "none" and not m.tiers


# ── languages ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("q, top", [("kodi fried rice", "Chicken Fried Rice"), ("mamsam kura", "Mutton Curry"),
                                    ("chepala pulusu", "Fish Curry"), ("కోడి బిర్యానీ", "Chicken Dum Biryani"),
                                    ("మటన్ బిర్యానీ", "Mutton Dum Biryani"), ("anda biryani", "Egg Biryani"),
                                    ("bhai ek chicken biryani bhej do", "Chicken Dum Biryani"),
                                    ("Madhapur lo chicken biryani kavali", "Chicken Dum Biryani"),
                                    ("2 chicken 65", "Chicken 65"), ("idli 2", "Idli (2 pcs)"),
                                    ("chicken biryani full", "Chicken Dum Biryani (Full)")])
def test_mixed_language_requests(u, idx, q, top):
    assert best(u(q), idx)[0] == top


def test_dosa_karam_lekunda(u, idx):
    m = u("dosa karam lekunda")
    assert m.understood.max_spice == 1 and best(m, idx)[0] == "Plain Dosa"
    assert all("dosa" in idx.names[d].lower() or idx.dishes[d]["category"] == "tiffin" for d in m.tiers)


# ── properties over the whole catalogue ──────────────────────────────────
def test_every_alias_and_name_finds_its_own_dish(db_conn, u, idx):
    """All 1,815 aliases and 319 names, typed exactly: the dish itself is the exact match."""
    rows = db_conn.execute("select dish_id, alias from public.dish_aliases union all "
                           "select dish_id, name from public.dishes").fetchall()
    wrong = []
    for r in rows:
        m = u(r["alias"])
        if m.tiers.get(r["dish_id"]) != EXACT:
            wrong.append((r["alias"], r["dish_id"], best(m, idx)[:2]))
    assert not wrong, f"{len(wrong)} aliases miss their dish, e.g. {wrong[:10]}"


@pytest.mark.parametrize("filler", sorted(FILLERS - SOFT))
def test_chat_words_are_never_typo_corrected_or_matched(u, filler):
    m = u(f"{filler} chicken biryani")
    assert filler not in m.understood.corrections and filler not in m.understood.unmatched_words
