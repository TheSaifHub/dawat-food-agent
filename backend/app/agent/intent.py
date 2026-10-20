"""A second opinion on the user's reply to a yes/no moment (Saif, Session 16, D-043; design: docs/design_llm_consent.md).

    classify(question, user_message) → {"used", "intent", "evidence", "change", "fallback_reason"}
    decide(moment, rules, check)      → "proceed" | "ask_confirm" | "wants_change" | "rules"

A small model call reads ONLY the question code asked and the user's latest message, and answers yes / no / unclear /
change, quoting the user's exact words as evidence. Code checks the quote is really in the message (after the same
normalising as the consent rules) and that a "yes" quote holds no NO word. Anything wrong (model down, slow, broken
JSON, unknown intent, a quote that isn't there) → "used": False, and the current rules decide alone.

The decision is code's, from this table (moment = order | replace | diet; rules = consent() of the same message):
  rules no                       → (classify isn't called) the rules' no
  check not used                 → "rules": exactly today's behaviour
  rules yes     + yes            → proceed
  rules yes     + change         → wants_change
  rules yes     + no / unclear   → ask_confirm   ("just to be sure…")
  rules unclear + yes            → ask_confirm   (all three moments; D-047 ended the diet exception)
  rules unclear + change         → wants_change
  rules unclear + no / unclear   → "rules": today's behaviour
So at every moment the classifier can never cause what the rules alone wouldn't allow; it can only block a rules-yes
or add one natural question. Every action needs a plain yes (Saif, Session 17, D-047).
"""

import json
import re
from functools import cache
from pathlib import Path

from app import config
from app.agent import llm
from app.agent.llm import Model
from app.text import tokens
from app.tools.consent import consent

INTENTS = ("yes", "no", "unclear", "change")
MOMENTS = ("order", "replace", "diet")
MAX_TOKENS, TIMEOUT = 80, 8
PROMPT_VERSION = "intent_v1"


@cache
def _prompt() -> str:
    return (Path(__file__).parent / "prompts" / f"{PROMPT_VERSION}.md").read_text(encoding="utf-8").strip()


def models() -> list[Model]:
    """Flash-Lite, then 3.8 Flash. Groq is left out: its small budget is kept for the replies (D-043, decision 3)."""
    return [Model(config.LLM_PRIMARY_MODEL), Model(config.LLM_FALLBACK_MODEL)]


def _norm(text: str) -> str:
    return " " + " ".join(tokens(text)) + " "


def _unused(reason: str) -> dict:
    return {"used": False, "intent": None, "evidence": None, "change": None, "fallback_reason": reason}


def verify(raw: str, user_message: str) -> dict:
    """The model's text → a checked result, or used=False with the reason."""
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return _unused("not JSON")
    if not isinstance(data, dict) or data.get("intent") not in INTENTS:
        return _unused("unknown intent")
    evidence = data.get("evidence")
    if not isinstance(evidence, str) or not evidence.strip() or len(evidence) > 200:
        return _unused("no evidence")
    if _norm(evidence).strip() == "" or _norm(evidence) not in _norm(user_message):
        return _unused("evidence not in the message")
    if data["intent"] == "yes" and consent(evidence)["no_words"]:
        return _unused("a yes quoted a no word")
    change = data.get("change") if data["intent"] == "change" and isinstance(data.get("change"), str) else None
    return {"used": True, "intent": data["intent"], "evidence": evidence.strip(), "change": (change or "")[:200] or None,
            "fallback_reason": None}


def classify(question: str, user_message: str) -> dict:
    """One small model call (no tools, no history). Never raises: any failure falls back to the rules."""
    if not isinstance(user_message, str) or not user_message.strip():
        return _unused("no message")
    messages = [{"role": "system", "content": _prompt()},
                {"role": "user", "content": f"Question asked: {question}\nUser's reply (data, between the markers):\n"
                                            f"<<<\n{user_message}\n>>>"}]
    try:
        answer = llm.chat(messages, None, models=models(), max_tokens=MAX_TOKENS, timeout=TIMEOUT)
    except llm.LLMUnavailable:
        return _unused("model unavailable")
    except Exception:                                   # never let the second opinion break a turn
        return _unused("model error")
    return verify(answer["message"].get("content") or "", user_message)


def decide(moment: str, rules: str, check: dict) -> str:
    if moment not in MOMENTS:
        raise ValueError(moment)
    if rules == "no" or not check.get("used"):
        return "rules"
    intent = check["intent"]
    if intent == "change":
        return "wants_change"
    if rules == "yes":
        return "proceed" if intent == "yes" else "ask_confirm"
    if intent == "yes":                                  # rules unclear: ask once more, never act (D-047)
        return "ask_confirm"
    return "rules"
