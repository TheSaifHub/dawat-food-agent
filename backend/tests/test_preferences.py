"""get_preferences, save_preference, delete_preference (D-027) against the real database, rolled back.

Saif's rule under test: a preference changes only when the user asks in their latest message (or says yes to the
offer, or uses the settings screen). From chat, in two steps (D-045): the request gets a question, and only the
user's yes in the next message changes anything. Nothing else, including the whole ordering flow, ever writes one. One user can
never see or change another's."""

import re
import uuid
from pathlib import Path

import pytest
from psycopg import errors

from app.tools.cart import add_to_cart, set_delivery, view_cart
from app.tools.dishes import search_dishes
from app.tools.history import get_user_history
from app.tools.orders import confirm_cart, place_order
from app.tools.preferences import delete_preference, get_preferences, save_preference

ASK = "Remember I'm vegetarian please"


@pytest.fixture
def users(demo_users):
    arjun, family, priya = demo_users
    return {"arjun": arjun, "family": family, "priya": priya}


def rows(db, user_id):
    return {r["key"]: (r["value"], r["source"]) for r in db.execute(
        "select key, value, source from public.user_preferences where user_id = %s", (user_id,))}


def chat(db, user_id, key, value, words, message, source="chat_request", offers=()):
    return save_preference(db, user_id, key, value, source, user_words=words, user_message=message, offers=offers)


def two_steps(db, user_id, key, value, words, message, yes="haan"):
    """D-045: the request gives an offer (nothing saved); the yes in the next message saves exactly that offer."""
    offer = chat(db, user_id, key, value, words, message)
    assert offer["status"] == "confirm_preference", offer
    return chat(db, user_id, key, value, yes, yes, source="chat_confirmed", offers=[offer["offer"]])


# ── viewing ──────────────────────────────────────────────────────────────
def test_view_shows_the_saved_preferences_with_labels_and_how_they_were_saved(db, users):
    res = get_preferences(db, users["priya"])
    p = res["preferences"]
    assert res["status"] == "ok" and list(p) == ["diet", "max_spice", "default_area", "language"]
    assert p["diet"]["value"] == "vegetarian" and p["diet"]["label"] == "Vegetarian"
    assert p["max_spice"]["value"] == 1 and p["max_spice"]["label"] == "Spice up to 1 of 3 (mild)"
    assert p["default_area"]["label"] == "Default delivery area: Madhapur"
    assert {v["source"] for v in p.values()} == {"seed"}


def test_view_with_nothing_saved(db, users):
    delete_preference(db, users["arjun"], "all", "settings")
    res = get_preferences(db, users["arjun"])
    assert res["status"] == "ok" and res["preferences"] == {} and "no saved" in res["message"]


# ── saving only on an explicit request ───────────────────────────────────
def test_an_explicit_request_only_asks_then_the_yes_saves_it(db, users):
    before = rows(db, users["arjun"])
    offer = chat(db, users["arjun"], "diet", "veg", "remember I'm vegetarian", ASK)
    assert offer["status"] == "confirm_preference" and rows(db, users["arjun"]) == before     # nothing saved yet
    assert offer["offer"] == {"action": "save", "key": "diet", "value": "vegetarian"}
    assert "Vegetarian" in offer["message"] and "chat_confirmed" in offer["message"]
    res = chat(db, users["arjun"], "diet", "veg", "haan", "haan", source="chat_confirmed", offers=[offer["offer"]])
    assert res["status"] == "ok" and res["value"] == "vegetarian" and res["previous"] == "non_vegetarian"
    assert rows(db, users["arjun"])["diet"] == ("vegetarian", "chat_confirmed")
    assert "forget it any time" in res["message"]


def test_a_yes_saves_only_the_change_that_was_offered(db, users):
    before = rows(db, users["arjun"])
    offer = {"action": "save", "key": "max_spice", "value": 1}
    for offers, value in (((), 1), ([offer], 2), ([{**offer, "action": "delete"}], 1),
                          ([{**offer, "key": "diet"}], 1)):
        res = chat(db, users["arjun"], "max_spice", value, "haan", "haan", source="chat_confirmed", offers=offers)
        assert res["status"] == "not_requested", (offers, value)
    assert rows(db, users["arjun"]) == before
    for message in ("haan, but make it 2", "ok thanks", "hmm", "yes?"):                # the whole message must be a yes
        res = chat(db, users["arjun"], "max_spice", 1, "haan" if "haan" in message else message.split(",")[0],
                   message, source="chat_confirmed", offers=[offer])
        assert res["status"] != "ok", message
    res = chat(db, users["arjun"], "max_spice", 1, "haan", "Haan", source="chat_confirmed", offers=[offer])
    assert res["status"] == "ok" and rows(db, users["arjun"])["max_spice"] == (1, "chat_confirmed")


@pytest.mark.parametrize("words, message", [
    ("remember I'm vegetarian", "Show me some biryani in Gachibowli"),   # quoted words aren't in this message
    ("veg", "show me vegetables"),                                       # only whole words count
    ("yes", "no thanks"),
])
def test_words_not_in_the_latest_message_change_nothing(db, users, words, message):
    before = rows(db, users["arjun"])
    res = chat(db, users["arjun"], "diet", "vegetarian", words, message)
    assert res["status"] == "not_requested"
    assert rows(db, users["arjun"]) == before


def test_a_remark_that_only_mentions_a_preference_saves_nothing_without_the_question(db, users):
    """The quote check proves whose words they are, not that they mean "save" ("I'm vegetarian, show me biryani").
    D-045: that's now covered by the second step: such a message only gets the question, never a change."""
    before = rows(db, users["arjun"])
    res = chat(db, users["arjun"], "diet", "vegetarian", "i'm VEGETARIAN", "I'm vegetarian, show me biryani")
    assert res["status"] == "confirm_preference" and rows(db, users["arjun"]) == before


@pytest.mark.parametrize("message", ["is the paneer biryani veg?", "am I saved as vegetarian?", "veg hai kya?",
                                     "can you forget my diet?"])
def test_a_question_is_never_a_request(db, users, message):
    before = rows(db, users["priya"])
    words = message.rstrip("?").split()[-1]
    assert chat(db, users["priya"], "diet", "non_vegetarian", words, message)["status"] == "not_requested"
    res = delete_preference(db, users["priya"], "diet", "chat_request", user_words=words, user_message=message)
    assert res["status"] == "not_requested" and rows(db, users["priya"]) == before


@pytest.mark.parametrize("words, message", [(None, ASK), ("", ASK), ("?!", ASK), (ASK, None), ("x" * 301, ASK),
                                            (ASK, "y" * 2001), (123, ASK)])
def test_chat_writes_need_the_users_words_and_message(db, users, words, message):
    before = rows(db, users["arjun"])
    assert chat(db, users["arjun"], "diet", "vegetarian", words, message)["status"] == "invalid_input"
    assert rows(db, users["arjun"]) == before


@pytest.mark.parametrize("source", [None, "", "seed", "agent", "inferred", "CHAT_REQUEST"])
def test_only_the_three_sources_are_accepted(db, users, source):
    before = rows(db, users["arjun"])
    res = save_preference(db, users["arjun"], "diet", "vegetarian", source, user_words=ASK, user_message=ASK)
    assert res["status"] == "invalid_input" and rows(db, users["arjun"]) == before


def test_settings_screen_needs_no_quote(db, users):
    res = save_preference(db, users["arjun"], "language", "Telugu", "settings")
    assert res["status"] == "ok" and rows(db, users["arjun"])["language"] == ("te", "settings")


# ── values are checked and normalised ────────────────────────────────────
@pytest.mark.parametrize("key, value, stored", [
    ("diet", "Veg", "vegetarian"), ("diet", "pure veg", "vegetarian"), ("diet", "non-veg", "non_vegetarian"),
    ("diet", "Non Vegetarian", "non_vegetarian"), ("diet", "eggetarian", "eggetarian"),
    ("max_spice", 0, 0), ("max_spice", 3, 3), ("max_spice", " 2 ", 2),
    ("language", "English", "en"), ("language", "hinglish", "hinglish"), ("language", "te", "te"),
    ("default_area", "Madhapur", "madhapur"), ("default_area", "gachibouli", "gachibowli"),   # fuzzy ≥ 88 (D-023)
])
def test_values_are_normalised(db, users, key, value, stored):
    res = save_preference(db, users["family"], key, value, "settings")
    assert res["status"] == "ok" and res["value"] == stored
    assert rows(db, users["family"])[key][0] == stored


@pytest.mark.parametrize("key, value", [
    ("diet", "vegan"), ("diet", None), ("diet", ["vegetarian"]), ("max_spice", 4), ("max_spice", -1),
    ("max_spice", True), ("max_spice", 1.5), ("max_spice", "spicy"), ("language", "hindi"), ("language", 1),
    ("default_area", ""), ("default_area", 5), ("email", "a@b.c"), ("all", "x"), (None, "vegetarian"),
])
def test_bad_values_and_keys_are_refused(db, users, key, value):
    before = rows(db, users["family"])
    assert save_preference(db, users["family"], key, value, "settings")["status"] == "invalid_input"
    assert rows(db, users["family"]) == before


@pytest.mark.parametrize("area, status", [("madhapoor", "confirm_area"), ("Manikonda", "outside_coverage"),
                                          ("Hyderabad", "needs_area"), ("Narnia", "unknown_area")])
def test_an_area_that_isnt_clearly_ours_is_not_saved(db, users, area, status):
    before = rows(db, users["family"])
    res = save_preference(db, users["family"], "default_area", area, "settings")
    assert res["status"] == status and res["message"].startswith("Nothing was saved")
    assert rows(db, users["family"]) == before


def test_saving_again_replaces_the_value_and_records_the_new_source(db, users):
    assert two_steps(db, users["priya"], "max_spice", 2, "remember medium spice", "ok remember medium spice")["status"] == "ok"
    res = save_preference(db, users["priya"], "max_spice", 0, "settings")
    assert res["previous"] == 2 and rows(db, users["priya"])["max_spice"] == (0, "settings")
    assert db.execute("select count(*) as n from public.user_preferences where user_id = %s and key = 'max_spice'",
                      (users["priya"],)).fetchone()["n"] == 1


# ── deleting ─────────────────────────────────────────────────────────────
def test_forget_one_preference(db, users):
    before = rows(db, users["priya"])
    offer = delete_preference(db, users["priya"], "diet", "chat_request", user_words="forget that I'm vegetarian",
                              user_message="Please forget that I'm vegetarian")
    assert offer["status"] == "confirm_preference" and offer["offer"] == {"action": "delete", "key": "diet"}
    assert "Vegetarian" in offer["message"] and rows(db, users["priya"]) == before
    assert delete_preference(db, users["priya"], "diet", "chat_confirmed", user_words="yes",
                             user_message="yes")["status"] == "not_requested"              # no offer passed
    assert delete_preference(db, users["priya"], "max_spice", "chat_confirmed", user_words="yes", user_message="yes",
                             offers=[offer["offer"]])["status"] == "not_requested"         # a different key
    res = delete_preference(db, users["priya"], "diet", "chat_confirmed", user_words="yes", user_message="yes",
                            offers=[offer["offer"]])
    assert res["status"] == "ok" and res["deleted"] == ["diet"]
    assert set(rows(db, users["priya"])) == {"max_spice", "default_area", "language"}


def test_forgetting_what_isnt_saved_asks_nothing(db, users):
    delete_preference(db, users["arjun"], "all", "settings")
    res = delete_preference(db, users["arjun"], "diet", "chat_request", user_words="forget my diet",
                            user_message="forget my diet")
    assert res["status"] == "not_saved"


def test_forget_everything(db, users):
    res = delete_preference(db, users["priya"], "all", "settings")
    assert res["deleted"] == ["diet", "max_spice", "default_area", "language"] and rows(db, users["priya"]) == {}
    assert delete_preference(db, users["priya"], "all", "settings")["status"] == "not_saved"


def test_forgetting_needs_an_explicit_request_too(db, users):
    before = rows(db, users["priya"])
    res = delete_preference(db, users["priya"], "diet", "chat_request", user_words="forget I'm vegetarian",
                            user_message="what's good in Madhapur?")
    assert res["status"] == "not_requested" and rows(db, users["priya"]) == before
    assert delete_preference(db, users["priya"], "diet", "chat_request")["status"] == "invalid_input"
    assert delete_preference(db, users["priya"], "diet", "seed")["status"] == "invalid_input"
    assert delete_preference(db, users["priya"], "email", "settings")["status"] == "invalid_input"
    assert rows(db, users["priya"]) == before


# ── one user can't see or change another's ───────────────────────────────
def test_users_only_see_their_own_preferences(db, users):
    two_steps(db, users["arjun"], "diet", "vegetarian", "remember I'm vegetarian", ASK)
    assert get_preferences(db, users["priya"])["preferences"]["max_spice"]["value"] == 1
    assert get_preferences(db, users["family"])["preferences"]["diet"]["value"] == "non_vegetarian"
    assert get_preferences(db, users["arjun"])["preferences"]["diet"]["value"] == "vegetarian"


def test_saving_or_forgetting_never_touches_another_user(db, users):
    others = {u: rows(db, users[u]) for u in ("priya", "family")}
    save_preference(db, users["arjun"], "language", "te", "settings")
    save_preference(db, users["arjun"], "default_area", "Charminar", "settings")
    delete_preference(db, users["arjun"], "diet", "settings")
    delete_preference(db, users["arjun"], "all", "settings")
    assert {u: rows(db, users[u]) for u in ("priya", "family")} == others


def test_an_unknown_user_gets_nothing_and_creates_nothing(db):
    ghost = uuid.uuid4()
    assert get_preferences(db, ghost)["status"] == "unknown_user"
    assert save_preference(db, ghost, "diet", "vegetarian", "settings")["status"] == "unknown_user"
    assert delete_preference(db, ghost, "all", "settings")["status"] == "unknown_user"
    assert rows(db, ghost) == {}


# ── nothing else ever saves a preference ─────────────────────────────────
def test_the_whole_ordering_flow_saves_no_preference(db, users):
    """Searching veg only, delivering somewhere new, ordering: a strong hint, and still nothing is saved."""
    before = {u: rows(db, users[u]) for u in users}
    found = search_dishes(db, "veg biryani", area="Kondapur", is_veg=True)
    assert found["status"] == "ok"
    pick = found["results"][0]
    set_delivery(db, users["arjun"], area="Kondapur")
    add_to_cart(db, users["arjun"], pick["item_id"], pick["branch"]["branch_id"])
    cart = view_cart(db, users["arjun"])
    confirm_cart(db, users["arjun"], cart["cart_id"], cart["quote_id"], source="website")
    assert place_order(db, users["arjun"], cart["cart_id"])["status"] == "ok"
    get_user_history(db, users["arjun"])
    assert {u: rows(db, users[u]) for u in users} == before


def test_no_other_code_writes_preferences():
    """A source scan: the only writers of user_preferences in app/ are the preferences tool and the demo-persona
    seeding (POST /demo/start, D-048), which writes only with source 'seed' and only for anonymous demo accounts."""
    app = Path(__file__).resolve().parent.parent / "app"
    writer = re.compile(r"(insert\s+into|update|delete\s+from)\s+public\.user_preferences", re.I)
    found = {str(p.relative_to(app)) for p in app.rglob("*.py") if writer.search(p.read_text(encoding="utf-8"))}
    assert found == {str(Path("tools/preferences.py")), str(Path("tools/demo.py"))}
    demo = (app / "tools" / "demo.py").read_text(encoding="utf-8")
    assert "values (%s, %s, %s, 'seed')" in demo and "source = 'seed'" in demo       # never a chat/settings source
    assert "is_anonymous" in demo


# ── the database backs it up ─────────────────────────────────────────────
def test_database_refuses_a_preference_without_a_source(db, users):
    with pytest.raises(errors.NotNullViolation), db.transaction():
        db.execute("insert into public.user_preferences (user_id, key, value) values (%s, 'diet', '\"vegetarian\"') "
                   "on conflict (user_id, key) do update set source = null", (users["arjun"],))


@pytest.mark.parametrize("source, value", [("inferred", '"en"'), ("settings", '"hindi"')])
def test_database_refuses_unknown_sources_and_languages(db, users, source, value):
    with pytest.raises(errors.CheckViolation), db.transaction():
        db.execute("update public.user_preferences set source = %s, value = %s::jsonb where user_id = %s and key = 'language'",
                   (source, value, users["arjun"]))
