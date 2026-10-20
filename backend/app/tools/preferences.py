"""get_preferences, save_preference, delete_preference (D-027). Plain-JSON results.

SAIF'S RULE: a preference is saved (or deleted) only when the user explicitly asks Dawat AI to ("remember I'm
vegetarian", "forget my spice level"), says yes to Dawat AI's offer to save one, or changes it on the website's
settings screen. Never inferred from what they order or search for, never silently.

How code enforces it (the LLM understands the request; code checks where it came from):
  · Every write declares its `source`: chat_request | chat_confirmed | settings. The database refuses a row
    without one (0008) and stores it, so the user can always see how each preference got there.
  · A chat write must quote the user's own words (`user_words`: the request, or their "yes" to the offer), and
    those words must appear in `user_message`, the user's latest message, which the agent runtime fills in from
    the conversation (Phase 6), never the LLM. A request remembered from earlier, or invented, is refused.
  · From chat, every change takes two steps (Saif, Session 16, D-045): chat_request changes nothing and returns
    the question to ask (confirm_preference); only the user's clear yes in their NEXT message, to that exact offer,
    changes it (chat_confirmed). A question ("is the paneer biryani veg?") is never a request.
  · This module is the only code that writes user_preferences (a test scans app/ for any other writer), so no
    other tool (search, cart, orders) can save a preference as a side effect.
Values are checked and normalised here ("veg" → vegetarian, "madhapoor" → Madhapur), never stored as given.
"""

import uuid

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.text import norm_alias
from app.tools.areas import resolve_area
from app.tools.reference import get_reference

KEYS = ("diet", "max_spice", "default_area", "language")
CHAT_SOURCES = ("chat_request", "chat_confirmed")
SOURCES = CHAT_SOURCES + ("settings",)
MAX_WORDS_LEN, MAX_MESSAGE_LEN = 300, 2000

DIETS = {"vegetarian": "vegetarian", "veg": "vegetarian", "pure veg": "vegetarian", "eggetarian": "eggetarian",
         "non vegetarian": "non_vegetarian", "non veg": "non_vegetarian", "nonveg": "non_vegetarian"}
LANGUAGES = {"en": "en", "english": "en", "hinglish": "hinglish", "te": "te", "telugu": "te"}
SPICE_WORDS = {0: "no spice", 1: "mild", 2: "medium", 3: "very spicy"}
DIET_LABELS = {"vegetarian": "Vegetarian", "eggetarian": "Eggetarian (vegetarian + egg)",
               "non_vegetarian": "Non-vegetarian"}
LANGUAGE_LABELS = {"en": "English", "hinglish": "Hinglish", "te": "Telugu"}
SOURCE_LABELS = {"chat_request": "you asked Dawat AI to remember it", "chat_confirmed": "you said yes when Dawat AI offered",
                 "settings": "you set it in your settings", "seed": "part of the demo account"}


def _invalid(message: str, **extra) -> dict:
    return {"status": "invalid_input", "message": message, **extra}


def _user_exists(conn: Connection, user_id: uuid.UUID) -> bool:
    return conn.execute("select 1 from public.users where user_id = %s", (user_id,)).fetchone() is not None


# A chat request to save or forget a preference must use a word about THAT preference (Phase 6 rule-breaker, D-044:
# "user_words" could be any words of the message, e.g. "chicken dum biryani", and delete a saved vegetarian diet).
KEY_WORDS = {
    "diet": {"veg", "vegetarian", "vegeterian", "vegitarian", "vegetarion", "nonveg", "eggetarian", "egg", "eggs",
             "meat", "diet", "vegan", "shakahari", "shakahaari", "mansahari", "maansahari", "jain", "శాకాహారి",
             "మాంసాహారి", "शाकाहारी", "मांसाहारी"},
    "max_spice": {"spice", "spicy", "spiciness", "mild", "teekha", "tikha", "teekhi", "karam", "kaaram", "hot",
                  "chilli", "chili", "mirchi", "కారం", "तीखा"},
    "default_area": {"area", "address", "location", "deliver", "delivery", "home", "office", "locality", "place"},
    "language": {"language", "english", "hinglish", "telugu", "hindi", "bhasha", "basha", "భాష", "తెలుగు", "हिंदी"},
    "all": {"all", "everything", "preferences", "preference", "saved", "sab", "sabkuch", "anni", "అన్నీ", "सब"},
}


def _about(key: str, user_words: str, value=None) -> bool:
    words = set(norm_alias(user_words).split())
    if words & KEY_WORDS.get(key, set()):
        return True
    if key == "default_area" and isinstance(value, str):                # "remember Kondapur" names the area itself
        return bool(words & set(norm_alias(value).split()))
    return False


def _check_request(source, user_words, user_message, key=None, value=None) -> dict | None:
    """None if this write is allowed; otherwise the refusal. Settings-screen writes are explicit by nature."""
    if source not in SOURCES:
        return _invalid(f"source must be one of {', '.join(SOURCES)}")
    if source == "settings":
        return None
    if not isinstance(user_words, str) or not norm_alias(user_words) or len(user_words) > MAX_WORDS_LEN:
        return _invalid("user_words must quote the user's own words asking to save or forget this (or their yes to "
                        "your offer), copied from their latest message")
    if not isinstance(user_message, str) or len(user_message) > MAX_MESSAGE_LEN:
        return _invalid("user_message (the user's latest message) is missing")
    if f" {norm_alias(user_words)} " not in f" {norm_alias(user_message)} ":
        return {"status": "not_requested",
                "message": "Nothing was changed: those words are not in the user's latest message. Only save or forget "
                           "a preference when the user asks in this message, or says yes to your offer to do it."}
    from app.tools.consent import _question, consent
    if source == "chat_confirmed" and consent(user_message)["consent"] != "yes":
        return {"status": "not_requested",
                "message": "Nothing was changed: chat_confirmed needs the user's latest message to be a clear yes to "
                           "your question."}
    if source == "chat_request" and _question(user_message):
        return {"status": "not_requested",
                "message": "Nothing was changed: the user asked a question, which is never a request to change their "
                           "preferences. Answer the question."}
    if source == "chat_request" and key is not None and not _about(key, user_words, value):
        return {"status": "not_requested",
                "message": f"Nothing was changed: the quoted words don't ask about {key}. Quote the user's own words "
                           "asking to remember or forget it."}
    return None


DIET_SAID = {**DIETS, "shakahari": "vegetarian", "shakahaari": "vegetarian", "శాకాహారి": "vegetarian",
             "शाकाहारी": "vegetarian", "mansahari": "non_vegetarian", "maansahari": "non_vegetarian",
             "మాంసాహారి": "non_vegetarian", "मांसाहारी": "non_vegetarian", "non vegetarian": "non_vegetarian"}
SPICE_SAID = {"no spice": 0, "not spicy": 0, "zero spice": 0, "mild": 1, "less spicy": 1, "medium": 2,
              "spicy": 3, "very spicy": 3, "hot": 3, "teekha": 3, "karam": 3, "kaaram": 3}
LANGUAGE_SAID = {**LANGUAGES, "తెలుగు": "te"}


# A chat request to forget must say so (D-046: "show all veg dishes" was offered as "forget everything").
FORGET_WORDS = {"forget", "delete", "remove", "clear", "reset", "erase", "unsave", "bhool", "bhul", "bhulo", "bhoolo",
                "bhool", "hatao", "hata", "mita", "mitao", "marchipo", "marchipondi", "maruchipo", "teeseyi",
                "మర్చిపో", "మర్చిపోండి", "తీసేయి", "भूल", "भूलो", "हटाओ", "मिटाओ"}


def _phrases_in(words: list[str], table: dict) -> set:
    """Values of the table's phrases found in the words, longest phrase first, without overlaps."""
    found, i = set(), 0
    while i < len(words):
        for size in (3, 2, 1):
            chunk = " ".join(words[i:i + size])
            if len(words[i:i + size]) == size and chunk in table:
                found.add(table[chunk])
                i += size
                break
        else:
            i += 1
    return found


def _said_value(conn: Connection, key: str, stored, user_words: str) -> bool:
    """D-046 (third rule-breaker run): a chat request must name the VALUE too, not just mention the preference
    ("show me veg biryani" can't become an offer to save non-vegetarian)."""
    words = norm_alias(user_words).split()
    if key == "diet":
        return stored in _phrases_in(words, DIET_SAID)
    if key == "max_spice":
        return stored in _phrases_in(words, SPICE_SAID) or str(stored) in words
    if key == "language":
        return stored in _phrases_in(words, LANGUAGE_SAID)
    ref = get_reference(conn)
    for size in (1, 2, 3):
        for i in range(len(words) - size + 1):
            got = resolve_area(ref, " ".join(words[i:i + size]))
            if got.get("status") == "ok" and got["area"]["area_id"] == stored:
                return True
    return False


def _offered(offers, action: str, key: str, value=None) -> bool:
    """Was exactly this change offered in the previous turn (a confirm_preference result, D-045)?"""
    return any(isinstance(o, dict) and o.get("action") == action and o.get("key") == key
               and (action == "delete" or o.get("value") == value) for o in offers or ())


NOT_OFFERED = {"status": "not_requested",
               "message": "Nothing was changed: you haven't asked the user about this change yet. Call again with "
                          "source chat_request (their own words asking for it); it gives you the question to ask."}


def _normalise(conn: Connection, key: str, value) -> tuple[object, dict | None]:
    """(stored value, None) or (None, refusal)."""
    if key == "diet":
        v = DIETS.get(norm_alias(value)) if isinstance(value, str) else None
        return (v, None) if v else (None, _invalid("diet must be vegetarian, eggetarian or non_vegetarian"))
    if key == "max_spice":
        if isinstance(value, str) and value.strip().isdigit():
            value = int(value.strip())
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 3:
            return None, _invalid("max_spice must be a whole number from 0 (no spice) to 3 (very spicy)")
        return value, None
    if key == "language":
        v = LANGUAGES.get(norm_alias(value)) if isinstance(value, str) else None
        return (v, None) if v else (None, _invalid("language must be en (English), hinglish or te (Telugu)"))
    if not isinstance(value, str) or not value.strip() or len(value) > 80:
        return None, _invalid("default_area must be an area name, e.g. 'Madhapur'")
    resolved = resolve_area(get_reference(conn), value)
    if resolved["status"] != "ok":
        return None, {"status": resolved["status"], "area_resolution": resolved,
                      "message": "Nothing was saved. " + resolved["message"]}
    return resolved["area"]["area_id"], None


def _label(ref, key: str, value) -> str:
    if key == "diet":
        return DIET_LABELS.get(value, str(value))
    if key == "max_spice":
        return f"Spice up to {value} of 3 ({SPICE_WORDS.get(value, '?')})"
    if key == "language":
        return LANGUAGE_LABELS.get(value, str(value))
    area = ref.areas.get(value)
    return f"Default delivery area: {area['name'] if area else value}"


def _all(conn: Connection, user_id: uuid.UUID) -> dict:
    ref = get_reference(conn)
    rows = conn.execute("select key, value, source, updated_at from public.user_preferences where user_id = %s "
                        "order by array_position(%s::text[], key)", (user_id, list(KEYS))).fetchall()
    return {r["key"]: {"value": r["value"], "label": _label(ref, r["key"], r["value"]), "source": r["source"],
                       "how_saved": SOURCE_LABELS[r["source"]], "saved_at": r["updated_at"].isoformat()} for r in rows}


# Diets that never get meat. Eggetarian counts too: the menu marks egg dishes non-veg like meat, so they can't be
# told apart, and the safe side is the vegetarian side (Saif, Session 16, D-039).
VEG_DIETS = ("vegetarian", "eggetarian")


def saved_diet(conn: Connection, user_id: uuid.UUID | None) -> str | None:
    """The user's saved diet, or None. Read-only: used by the planner and the chat's add_to_cart check."""
    if user_id is None:
        return None
    row = conn.execute("select value from public.user_preferences where user_id = %s and key = 'diet'",
                       (user_id,)).fetchone()
    return row["value"] if row and isinstance(row["value"], str) else None


def get_preferences(conn: Connection, user_id: uuid.UUID) -> dict:
    if not _user_exists(conn, user_id):
        return {"status": "unknown_user", "message": "Sign in again: this account has no Dawat profile."}
    prefs = _all(conn, user_id)
    return {"status": "ok", "preferences": prefs,
            "message": ("These are the only preferences the user saved. Show them exactly as given when asked; change or "
                        "forget one only when the user asks." if prefs else "The user has no saved preferences.")}


def save_preference(conn: Connection, user_id: uuid.UUID, key: str, value, source: str,
                    user_words: str | None = None, user_message: str | None = None, offers=()) -> dict:
    """Call ONLY when the user asked to remember this, or said yes to your offer to (see the module docstring).
    From chat it takes two steps (D-045): chat_request saves nothing and returns the question to ask
    (confirm_preference); chat_confirmed saves only if that exact change is in `offers` (the confirm_preference
    results of the previous turn, passed by the agent runtime) and the user's latest message is a clear yes."""
    if key not in KEYS:
        return _invalid(f"key must be one of {', '.join(KEYS)}")
    refused = _check_request(source, user_words, user_message, key, value)
    if refused:
        return refused
    stored, refused = _normalise(conn, key, value)
    if refused:
        return refused
    if not _user_exists(conn, user_id):
        return {"status": "unknown_user", "message": "Sign in again: this account has no Dawat profile."}
    if source == "chat_request" and not _said_value(conn, key, stored, user_words):
        return {"status": "not_requested",
                "message": "Nothing was changed: the user's words don't name this value. Save only what they asked "
                           "for, in their own words."}
    if source == "chat_request":
        label = _label(get_reference(conn), key, stored)
        return {"status": "confirm_preference", "offer": {"action": "save", "key": key, "value": stored},
                "label": label,
                "message": f"Nothing is saved yet. Ask the user, in their language and script, whether to save "
                           f"\"{label}\" to their preferences. Call save_preference with source chat_confirmed only "
                           "after their clear yes in their next message."}
    if source == "chat_confirmed" and not _offered(offers, "save", key, stored):
        return NOT_OFFERED
    old = conn.execute("select value from public.user_preferences where user_id = %s and key = %s for update",
                       (user_id, key)).fetchone()
    conn.execute("""insert into public.user_preferences (user_id, key, value, source) values (%s, %s, %s, %s)
                    on conflict (user_id, key) do update set value = excluded.value, source = excluded.source""",
                 (user_id, key, Jsonb(stored), source))
    prefs = _all(conn, user_id)
    return {"status": "ok", "key": key, "value": stored, "label": prefs[key]["label"],
            "previous": old["value"] if old else None, "preferences": prefs,
            "message": f"Saved: {prefs[key]['label']}. Tell the user exactly what was saved, and that they can ask you "
                       "to forget it any time."}


def delete_preference(conn: Connection, user_id: uuid.UUID, key: str, source: str,
                      user_words: str | None = None, user_message: str | None = None, offers=()) -> dict:
    """Forget one saved preference, or key="all" for every one. Same rule as saving: only when the user asks, and
    from chat in the same two steps (D-045)."""
    if key not in KEYS + ("all",):
        return _invalid(f"key must be one of {', '.join(KEYS)}, or all")
    refused = _check_request(source, user_words, user_message, key)
    if refused:
        return refused
    if source == "chat_request" and not set(norm_alias(user_words).split()) & FORGET_WORDS:
        return {"status": "not_requested",
                "message": "Nothing was changed: the quoted words don't ask to forget anything. Quote the user's own "
                           "words asking you to forget it."}
    if not _user_exists(conn, user_id):
        return {"status": "unknown_user", "message": "Sign in again: this account has no Dawat profile."}
    keys = list(KEYS) if key == "all" else [key]
    if source == "chat_request":
        saved = _all(conn, user_id)
        if not any(k in saved for k in keys):
            return {"status": "not_saved", "preferences": saved,
                    "message": "There was nothing saved to forget" + ("." if key == "all" else f" for {key}.")}
        what = "all your saved preferences" if key == "all" else f"your saved {key} ({saved[key]['label']})"
        return {"status": "confirm_preference", "offer": {"action": "delete", "key": key}, "label": what,
                "message": f"Nothing is forgotten yet. Ask the user, in their language and script, whether to forget "
                           f"this ({what}). Call delete_preference with source chat_confirmed only after their clear yes in "
                           "their next message."}
    if source == "chat_confirmed" and not _offered(offers, "delete", key):
        return NOT_OFFERED
    gone = [r["key"] for r in conn.execute("delete from public.user_preferences where user_id = %s and key = any(%s) "
                                           "returning key", (user_id, keys)).fetchall()]
    if not gone:
        return {"status": "not_saved", "preferences": _all(conn, user_id),
                "message": "There was nothing saved to forget" + ("." if key == "all" else f" for {key}.")}
    return {"status": "ok", "deleted": sorted(gone, key=KEYS.index), "preferences": _all(conn, user_id),
            "message": "Forgotten: " + ", ".join(sorted(gone, key=KEYS.index)) + ". Tell the user exactly this."}
