"""Backend configuration, read from environment variables.

Locally, values come from backend/.env (loaded below). On Render, they come
from the dashboard's environment variables. Nothing secret is hard-coded here.
"""

import os

from dotenv import load_dotenv

load_dotenv()

DEFAULT_ALLOWED_ORIGINS = "http://localhost:3000"


def parse_allowed_origins(raw: str) -> list[str]:
    """Turn "https://a.com, https://b.com/" into ["https://a.com", "https://b.com"].

    Browsers send the Origin header without a trailing slash, so one is stripped
    here; otherwise a copy-pasted Vercel URL would silently fail to match.
    A wildcard is refused outright rather than quietly allowed.
    """
    origins = [o.strip().rstrip("/") for o in raw.split(",")]
    origins = [o for o in origins if o]

    if "*" in origins:
        raise ValueError("ALLOWED_ORIGINS must list explicit origins; '*' is not allowed.")
    if not origins:
        raise ValueError("ALLOWED_ORIGINS is empty; set at least one origin.")
    return origins


def resolve_allowed_origins(env_value: str | None) -> list[str]:
    """Unset or blank (e.g. `ALLOWED_ORIGINS=` copied straight from .env.example) means the local default."""
    if env_value is None or not env_value.strip():
        env_value = DEFAULT_ALLOWED_ORIGINS
    return parse_allowed_origins(env_value)


ALLOWED_ORIGINS = resolve_allowed_origins(os.getenv("ALLOWED_ORIGINS"))


def blank_to_none(value: str | None) -> str | None:
    """`NAME=` copied from .env.example means "not set", not an empty string."""
    return value.strip() if value and value.strip() else None


# Supabase (Phase 4). Optional at import time so /health works without them; the auth and database
# layers refuse with a clear 503 if they are missing when actually needed.
SUPABASE_URL = (blank_to_none(os.getenv("SUPABASE_URL")) or "").rstrip("/") or None
DATABASE_URL = blank_to_none(os.getenv("DATABASE_URL"))

# D-053: how often (seconds) the in-memory reference copy reads its one-row version stamp. Tests use 0.
REFERENCE_CHECK_S = float(blank_to_none(os.getenv("REFERENCE_CHECK_S")) or 60)

# Dawat AI's models, tried in this order, once each (D-031/D-032; chain from Saif, Session 15, D-036), in LiteLLM
# "provider/model" form. Blank means these defaults. Google's free quotas are per model, so a rate limit on
# Flash-Lite leaves 3.8 Flash available; Groq is last because its free 8,000 tokens a minute fit only one step.
DEFAULT_LLM_PRIMARY_MODEL = "gemini/gemini-3.5-flash-lite"
DEFAULT_LLM_FALLBACK_MODEL = "gemini/gemini-3.8-flash"
DEFAULT_LLM_FALLBACK_2_MODEL = "groq/openai/gpt-oss-120b"
LLM_PRIMARY_MODEL = blank_to_none(os.getenv("LLM_PRIMARY_MODEL")) or DEFAULT_LLM_PRIMARY_MODEL
LLM_FALLBACK_MODEL = blank_to_none(os.getenv("LLM_FALLBACK_MODEL")) or DEFAULT_LLM_FALLBACK_MODEL
LLM_FALLBACK_2_MODEL = blank_to_none(os.getenv("LLM_FALLBACK_2_MODEL")) or DEFAULT_LLM_FALLBACK_2_MODEL

# D-048: chat messages per IST day across ALL users, to protect the free Gemini quota. 150 is a conservative
# placeholder until Saif reads Gemini 3.5 Flash-Lite's requests/day; then about a third of it (one message makes
# about 2–4 model calls). 0 turns chat off.
DEFAULT_CHAT_DAILY_CAP = 150
CHAT_DAILY_CAP = int(blank_to_none(os.getenv("CHAT_DAILY_CAP")) or DEFAULT_CHAT_DAILY_CAP)

# Phase 8 (D-061): Razorpay TEST mode only. Both blank = payments are not configured (the payment routes answer 503;
# browsing, the cart and the chat still work). A live key (rzp_live_…) is refused by app/payments/razorpay.py.
RAZORPAY_KEY_ID = blank_to_none(os.getenv("RAZORPAY_KEY_ID"))
RAZORPAY_KEY_SECRET = blank_to_none(os.getenv("RAZORPAY_KEY_SECRET"))

# D-062: which payment gateway the payment routes use. "simulated" (the default) is a local stand-in that needs no
# account and no keys: same routes, same HMAC check, test payment ids, fixed test card/UPI values only.
# "razorpay" is the real test-mode path (D-061), kept for later. Anything else = payments not configured.
PAYMENT_GATEWAY = (blank_to_none(os.getenv("PAYMENT_GATEWAY")) or "simulated").strip().lower()
# Signs the simulated gateway's payments. Blank → a random secret per server process (fine for local use; a restart
# only invalidates checkouts that were open at that moment).
PAYMENT_SIM_SECRET = blank_to_none(os.getenv("PAYMENT_SIM_SECRET"))
