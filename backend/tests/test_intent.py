"""The LLM intent check (D-043): quote verification, the decision table, and the safety property. Full rigour:
this sits in front of consent. No real model is called."""

import itertools

import pytest

from app.agent import intent, llm
from app.agent.intent import classify, decide, verify
from app.tools.consent import consent
from tests import test_consent as corpus


# ─── verification ────────────────────────────────────────────────────────────────────────────────────────

MSG = "I'm ordering it for my boyfriend, please go ahead"


@pytest.mark.parametrize("raw, ok", [
    ('{"intent": "yes", "evidence": "please go ahead", "change": ""}', True),
    ('```json\n{"intent": "yes", "evidence": "Please Go Ahead"}\n```', True),            # case and code fences
    ('{"intent": "yes", "evidence": "go ahead please now"}', False),                     # not in the message
    ('{"intent": "yes", "evidence": ""}', False),
    ('{"intent": "maybe", "evidence": "please go ahead"}', False),
    ('{"intent": "yes"}', False),
    ("yes", False), ("", False), ("[1, 2]", False),
    ('{"intent": "yes", "evidence": "ahea"}', False),                                    # part of a word only
])
def test_only_a_well_formed_answer_with_a_real_quote_is_used(raw, ok):
    assert verify(raw, MSG)["used"] is ok, raw


def test_a_yes_that_quotes_a_no_word_is_not_used():
    assert verify('{"intent": "yes", "evidence": "no wait"}', "no wait, ok fine")["used"] is False
    assert verify('{"intent": "no", "evidence": "no wait"}', "no wait, ok fine")["used"] is True


def test_quotes_work_in_hinglish_and_telugu_script():
    assert verify('{"intent": "yes", "evidence": "bhej do"}', "theek hai bhai, dost ke liye hai, bhej do")["used"]
    assert verify('{"intent": "yes", "evidence": "ఆర్డర్ పెట్టండి"}', "సరే, ఆర్డర్ పెట్టండి")["used"]
    assert verify('{"intent": "change", "evidence": "raita hata do", "change": "remove raita"}',
                  "haan order kar do, lekin raita hata do")["change"] == "remove raita"


def test_classify_falls_back_when_the_model_is_down_or_odd(monkeypatch):
    monkeypatch.setattr(llm, "chat", lambda *a, **k: (_ for _ in ()).throw(llm.LLMUnavailable([])))
    assert classify("Place the order for ₹341?", MSG) == {"used": False, "intent": None, "evidence": None,
                                                          "change": None, "fallback_reason": "model unavailable"}
    monkeypatch.setattr(llm, "chat", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert classify("q", MSG)["fallback_reason"] == "model error"
    assert classify("q", "")["used"] is False


def test_classify_sends_only_the_question_and_the_message(monkeypatch):
    seen = {}

    def fake(messages, tools=None, **kw):
        seen.update(messages=messages, tools=tools, kw=kw)
        return {"message": {"content": '{"intent": "yes", "evidence": "please go ahead"}', "tool_calls": []}}
    monkeypatch.setattr(llm, "chat", fake)
    out = classify("Place the order for ₹341?", MSG)
    assert out["used"] and out["intent"] == "yes"
    assert [m["role"] for m in seen["messages"]] == ["system", "user"] and seen["tools"] is None
    assert "₹341" in seen["messages"][1]["content"] and MSG in seen["messages"][1]["content"]
    assert seen["kw"]["max_tokens"] == intent.MAX_TOKENS and [m.name for m in seen["kw"]["models"]][-1].startswith("gemini/")


# ─── the decision table ──────────────────────────────────────────────────────────────────────────────────

def used(i):
    return {"used": True, "intent": i, "evidence": "x", "change": None, "fallback_reason": None}


UNUSED = {"used": False}
TABLE = {  # (rules, llm intent or None) → (order/replace, diet)
    ("no", "yes"): ("rules", "rules"), ("no", "change"): ("rules", "rules"), ("no", None): ("rules", "rules"),
    ("yes", None): ("rules", "rules"), ("unclear", None): ("rules", "rules"),
    ("yes", "yes"): ("proceed", "proceed"), ("yes", "change"): ("wants_change", "wants_change"),
    ("yes", "no"): ("ask_confirm", "ask_confirm"), ("yes", "unclear"): ("ask_confirm", "ask_confirm"),
    ("unclear", "yes"): ("ask_confirm", "ask_confirm"),("unclear", "change"): ("wants_change", "wants_change"),
    ("unclear", "no"): ("rules", "rules"), ("unclear", "unclear"): ("rules", "rules"),
}


@pytest.mark.parametrize("key", list(TABLE))
def test_the_decision_table(key):
    rules, i = key
    check = used(i) if i else UNUSED
    want_order, want_diet = TABLE[key]
    assert decide("order", rules, check) == want_order
    assert decide("replace", rules, check) == want_order
    assert decide("diet", rules, check) == want_diet


def test_the_safety_property_over_the_whole_consent_corpus():
    """Even a classifier that ALWAYS says yes (with a valid quote) never makes an order, a replacement or a diet add
    proceed unless the rules alone already say yes (D-047: the diet question has no exception)."""
    messages = set(corpus.ENGLISH_YES + corpus.HINGLISH_YES + corpus.TELUGU_YES + corpus.HINDI_SCRIPT_YES +
                   corpus.ENGLISH_NO + corpus.HINGLISH_NO + corpus.TELUGU_NO + corpus.HINDI_SCRIPT_NO +
                   [m for m in corpus.UNCLEAR if isinstance(m, str)] + corpus.WITH_OTHER_WORDS + corpus.STILL_UNCLEAR +
                   corpus.STILL_NO + [MSG])
    checked = 0
    for message, moment in itertools.product(sorted(messages), ("order", "replace", "diet")):
        rules = consent(message)["consent"]
        verdict = decide(moment, rules, used("yes"))
        if verdict == "proceed":
            assert rules == "yes", (message, moment)
        if rules == "no":
            assert verdict == "rules", message
        checked += 1
    assert checked > 600


def test_an_unknown_moment_is_a_bug():
    with pytest.raises(ValueError):
        decide("pay", "yes", used("yes"))
