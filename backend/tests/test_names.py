"""Correcting near-miss restaurant names before the user sees them (D-041, failure F-3). Plain tests, plus the one
that matters most: numbers and everything that isn't a near-miss restaurant name are left exactly as written."""

import re

import pytest

from app.agent.loop import run_turn
from app.agent.names import correct_names
from tests.test_agent_loop import PROMPT, Script

RESULTS = [{"status": "ok", "results": [
    {"name": "Chicken Dum Biryani", "price": 240, "restaurant": {"name": "Annapurna"}},
    {"name": "Chicken Dum Biryani", "price": 370, "restaurant": {"name": "Hi-Tech Bawarchi"}},
    {"name": "Chicken Dum Biryani", "price": 360, "restaurant": {"name": "Madhapur Bawarchi"}},
    {"name": "Chicken Dum Biryani", "price": 260, "restaurant": {"name": "Shree Santhosh Family Dhaba"}}]},
    {"status": "ok", "plans": [{"restaurants": [{"restaurant": "Kritunga", "items": []}]}]}]


@pytest.mark.parametrize("written, fixed", [
    ("Try **Annapura** for ₹240.", "Try **Annapurna** for ₹240."),
    ("Biryani at Annapuurna.", "Biryani at Annapurna."),
    ("Hi-Tech Bawarchy has it for ₹370", "Hi-Tech Bawarchi has it for ₹370"),
    ("Shree Santosh Family Dhaba: ₹260", "Shree Santhosh Family Dhaba: ₹260"),
    ("మాధాపూర్ లో Annapura ₹240", "మాధాపూర్ లో Annapurna ₹240"),
    ("Kritnga plan is ready", "Kritunga plan is ready"),                   # names from plan results count too
])
def test_near_miss_names_are_corrected(written, fixed):
    out, fixes = correct_names(written, RESULTS)
    assert out == fixed and len(fixes) == 1


@pytest.mark.parametrize("text", [
    "Annapurna is ₹240", "Madhapur Bawarchi and Hi-Tech Bawarchi", "the annapura one is nice",
    "Hyderabad Bawarchi is not on our list", "Anand Bhavan is far",          # similar, but a different name
    "Chicken Dum Biryani for ₹240", "Paradise is far", "", "No restaurants here.",
])
def test_everything_else_is_left_exactly_as_written(text):
    assert correct_names(text, RESULTS) == (text, [])


def test_numbers_are_never_touched():
    text = "Annapura: ₹240, Annapura2 ₹250, 3 Annapura items, total ₹1,234.50"
    out, _ = correct_names(text, RESULTS)
    assert re.findall(r"\d[\d,.]*", out) == re.findall(r"\d[\d,.]*", text)
    assert "Annapura2" in out                                                  # a word with a digit is left alone


def test_no_tool_results_means_no_change():
    assert correct_names("Try Annapura", []) == ("Try Annapura", [])


def test_the_loop_shows_the_corrected_reply_saves_it_and_logs_the_fix(db):
    script = Script([("search_dishes", {"query": "chicken biryani", "area": "Madhapur"})], "PLACEHOLDER")
    real = script.__call__

    def reply_with_a_misspelling(messages, tools=None):
        out = real(messages, tools)
        if out["message"]["content"] == "PLACEHOLDER":
            names = re.findall(r'"restaurant":\{"name":"([^"]+)"', messages[-1]["content"])
            wrong = names[0][:-1] + names[0][-1] * 2                            # e.g. Annapurna → Annapurnaa
            out = {**out, "message": {"content": f"Try {wrong} first.", "tool_calls": []}}
            reply_with_a_misspelling.expected = (wrong, names[0])
        return out
    turn = run_turn(db, [], "biryani in Madhapur", None, chat=reply_with_a_misspelling, **PROMPT)
    wrong, right = reply_with_a_misspelling.expected
    assert turn.reply == f"Try {right} first." and turn.corrections == [[wrong, right]]
    assert turn.messages[-1] == {"role": "assistant", "content": f"Try {right} first."}       # history keeps the fix
    assert turn.traces[-1]["tool_name"] == "name_correction" and turn.traces[-1]["step"] == 2


def test_a_word_equally_close_to_two_real_names_is_left_alone():
    two = [{"results": [{"restaurant": {"name": "Bawarchi Grand"}}, {"restaurant": {"name": "Bawarchi Grant"}}]}]
    assert correct_names("Try Bawarchi Grane", two) == ("Try Bawarchi Grane", [])
    assert correct_names("Try Bawarchi Grnd", two)[0] == "Try Bawarchi Grand"      # clearly closer to one: fixed
