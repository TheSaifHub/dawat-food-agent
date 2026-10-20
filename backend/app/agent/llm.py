"""The one door to the LLMs (Phase 6a, D-031/D-032). Everything else in the agent calls chat(), never LiteLLM.

    chat(messages, tools) → {"message", "raw_message", "model", "attempts", "usage", "seconds"}
                            or raises LLMUnavailable (its .user_message is the friendly "busy" text)

How a turn reaches a model (free tiers: one request per model, never a loop):
  1. The primary model (Gemini 3.5 Flash-Lite), ONE request.
  2. If that fails in any way (429 rate limit, 503 overloaded, timeout, connection error, a 400 the provider
     didn't like, an empty answer), the fallback (Gemini 3.8 Flash, low thinking), ONE request.
  3. If that fails too, the last resort (Groq gpt-oss-120b), ONE request. Its free 8,000 tokens a minute fit only
     about one step of a turn (D-035), so it is last (Saif, Session 15, D-036).
  4. If all fail: LLMUnavailable. The chat says "Dawat AI is busy" instead of crashing.
  LiteLLM's own retries are switched off on every call (max_retries=0, num_retries=0): some of its code paths
  otherwise inherit the OpenAI client's default of 2 retries, which would triple the requests behind our back.
  tests/test_llm.py counts the real HTTP requests against a fake provider to prove it.
  A model whose API key is missing is skipped without a request ("not_configured").

Secrets: keys are passed per call, never logged. Every error text kept in `attempts` (which ends up in
agent_traces) goes through scrub(): Gemini's AI Studio API puts the key in the URL (?key=...), and a provider
error can echo that URL back.
"""

import os
import re
import time
from dataclasses import dataclass

# LiteLLM downloads its model price list from GitHub on import unless told to use its bundled copy: an outbound
# request at every server start, for prices we don't use. Must be set before the import.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

import litellm  # noqa: E402

from app import config  # noqa: E402

litellm.suppress_debug_info = True          # no "Give Feedback / Get Help" banners in the server log
litellm.turn_off_message_logging = True     # LiteLLM's own logs never carry the user's messages
litellm.telemetry = False

BUSY_MESSAGE = "Dawat AI is busy right now. Please try again in a minute."
TIMEOUT_SECONDS = 20        # per request; Flash-Lite answered in 1.3 s and Groq in 0.9 s when measured (D-031)
MAX_OUTPUT_TOKENS = 1024    # a chat reply or a tool call; keeps Groq's 8,000 tokens/minute usable as a fallback
MAX_ERROR_CHARS = 300

# Which environment variable holds each provider's key (the names in backend/.env.example).
PROVIDER_KEYS = {"gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY"}
# Extra LiteLLM options per model. 3.8 Flash thinks at "medium" by default, which took 10 s in D-031; an ordering
# step needs to pick a tool, not reason at length.
MODEL_OPTIONS = {"gemini/gemini-3.8-flash": {"reasoning_effort": "low"}}


@dataclass(frozen=True)
class Model:
    name: str                       # LiteLLM "provider/model", e.g. "groq/openai/gpt-oss-120b"
    api_key: str | None = None      # None: read from the provider's environment variable
    api_base: str | None = None     # None: the provider's real endpoint (tests point this at a fake server)

    @property
    def provider(self) -> str:
        return self.name.split("/", 1)[0]

    def key(self) -> str | None:
        if self.api_key is not None:
            return self.api_key
        env = PROVIDER_KEYS.get(self.provider)
        return config.blank_to_none(os.getenv(env)) if env else None


def default_models() -> list[Model]:
    return [Model(config.LLM_PRIMARY_MODEL), Model(config.LLM_FALLBACK_MODEL), Model(config.LLM_FALLBACK_2_MODEL)]


class LLMUnavailable(RuntimeError):
    """Every model failed. `attempts` says why (scrubbed); `user_message` is what the chat shows."""

    def __init__(self, attempts: list[dict]):
        self.attempts = attempts
        self.user_message = BUSY_MESSAGE
        super().__init__("; ".join(f"{a['model']}: {a['outcome']}" for a in attempts) or "no models configured")


class EmptyReply(Exception):
    """The model answered with neither text nor a tool call (e.g. a blocked or malformed function call)."""


# ─── errors ──────────────────────────────────────────────────────────────────────────────────────────────

_KINDS = [  # most specific first: ContextWindowExceededError is a BadRequestError
    (litellm.exceptions.ContextWindowExceededError, "too_long"),
    (litellm.exceptions.RateLimitError, "rate_limited"),
    (litellm.exceptions.ServiceUnavailableError, "overloaded"),
    (litellm.exceptions.Timeout, "timeout"),
    (litellm.exceptions.AuthenticationError, "auth"),
    (litellm.exceptions.PermissionDeniedError, "auth"),
    (litellm.exceptions.NotFoundError, "model_not_found"),
    (litellm.exceptions.BadRequestError, "bad_request"),
    (litellm.exceptions.InternalServerError, "provider_error"),
    (litellm.exceptions.APIConnectionError, "connection"),
    (EmptyReply, "empty_reply"),
]


def classify(error: BaseException) -> str:
    for cls, kind in _KINDS:
        if isinstance(error, cls):
            return kind
    status = getattr(error, "status_code", None)
    if status == 429:
        return "rate_limited"
    if status in (502, 503, 504):
        return "overloaded"
    return "error"


_SECRET_PATTERNS = [
    re.compile(r"([?&](?:key|api_key|apikey)=)[^&\s\"']+", re.I),      # Gemini's ?key=... in a URL
    re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+", re.I),                   # an Authorization header echoed back
    re.compile(r"()AIza[0-9A-Za-z_\-]{20,}"),                           # Google API key shape
    re.compile(r"()gsk_[0-9A-Za-z]{20,}"),                               # Groq API key shape
]


def scrub(text: str, extra_secrets: tuple[str, ...] = ()) -> str:
    """Remove every key we know of, and anything shaped like one, from an error text before it is kept."""
    for secret in (*extra_secrets, *(os.getenv(v) for v in PROVIDER_KEYS.values())):
        if secret and len(secret) >= 8:
            text = text.replace(secret, "[REDACTED]")
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(lambda m: m.group(1) + "[REDACTED]", text)
    return text


# ─── the call ────────────────────────────────────────────────────────────────────────────────────────────

def _normalise(message) -> dict:
    tool_calls = [{"id": tc.id, "name": tc.function.name, "arguments": tc.function.arguments or ""}
                  for tc in (message.tool_calls or [])]
    content = message.content if isinstance(message.content, str) and message.content.strip() else None
    if content is None and not tool_calls:
        raise EmptyReply("the model returned neither text nor a tool call")
    return {"content": content, "tool_calls": tool_calls}


def for_provider(messages: list[dict], provider: str) -> list[dict]:
    """Gemini gets assistant messages whole (its thought signatures must come back). Other providers get only the
    standard fields: Groq refuses the extras LiteLLM attaches to a Gemini message ("property 'images' is
    unsupported", seen live in 6c when a turn switched from Gemini to Groq)."""
    if provider == "gemini":
        return messages
    out = []
    for m in messages:
        if m.get("role") == "assistant":
            slim = {"role": "assistant", "content": m.get("content")}
            if m.get("tool_calls"):
                slim["tool_calls"] = [{"id": c["id"], "type": "function",
                                       "function": {"name": c["function"]["name"],
                                                    "arguments": c["function"]["arguments"]}}
                                      for c in m["tool_calls"]]
            m = slim
        out.append(m)
    return out


def _one_request(model: Model, key: str, messages: list[dict], tools: list[dict] | None,
                 max_tokens: int = MAX_OUTPUT_TOKENS, timeout: float = TIMEOUT_SECONDS) -> dict:
    messages = for_provider(messages, model.provider)
    kwargs = {"model": model.name, "messages": messages, "api_key": key, "timeout": timeout,
              "max_tokens": max_tokens, "max_retries": 0, "num_retries": 0}
    kwargs.update(MODEL_OPTIONS.get(model.name, {}))
    if model.api_base:
        kwargs["api_base"] = model.api_base
    if tools:
        kwargs["tools"] = tools
    response = litellm.completion(**kwargs)
    choice = response.choices[0]
    usage = getattr(response, "usage", None)
    return {"message": _normalise(choice.message),
            # Kept whole for the next request: Gemini 3 needs its thought signatures sent back with tool calls.
            "raw_message": choice.message.model_dump(),
            "finish_reason": choice.finish_reason,
            "usage": {"prompt_tokens": getattr(usage, "prompt_tokens", None),
                      "completion_tokens": getattr(usage, "completion_tokens", None)}}


def chat(messages: list[dict], tools: list[dict] | None = None, *, models: list[Model] | None = None,
         max_tokens: int | None = None, timeout: float | None = None) -> dict:
    """One assistant step: each model in order, once. Raises LLMUnavailable if all fail."""
    attempts = []
    for model in models if models is not None else default_models():
        key = model.key()
        if key is None:
            attempts.append({"model": model.name, "outcome": "not_configured", "status_code": None,
                             "seconds": 0.0, "error": f"no API key for provider '{model.provider}'"})
            continue
        started = time.perf_counter()
        try:
            result = _one_request(model, key, messages, tools, max_tokens or MAX_OUTPUT_TOKENS,
                                  timeout or TIMEOUT_SECONDS)
        except Exception as error:      # any provider failure → record it (scrubbed) and try the next model
            attempts.append({"model": model.name, "outcome": classify(error),
                             "status_code": getattr(error, "status_code", None),
                             "seconds": round(time.perf_counter() - started, 2),
                             "error": scrub(f"{type(error).__name__}: {error}", (key,))[:MAX_ERROR_CHARS]})
            continue
        seconds = round(time.perf_counter() - started, 2)
        attempts.append({"model": model.name, "outcome": "ok", "status_code": 200, "seconds": seconds, "error": None})
        return {**result, "model": model.name, "attempts": attempts, "seconds": seconds}
    raise LLMUnavailable(attempts)
