"""app.agent.llm (Phase 6a, D-032): primary once → fallback once → "Dawat AI is busy". No real provider is called.

A local fake server plays both providers (Gemini's generateContent and Groq's OpenAI-style chat/completions),
answering from a script and counting every HTTP request, so "no hidden retries" is measured, not assumed.
Fake keys are deliberately not key-shaped (the guard hook refuses anything that looks like a real one); the scrub
tests build key-shaped strings at runtime.
"""

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app import config
from app.agent import llm
from app.agent.llm import BUSY_MESSAGE, LLMUnavailable, Model, chat, scrub

GEMINI_KEY, GROQ_KEY = "test-gemini-key-1234", "test-groq-key-5678"
HELLO = [{"role": "user", "content": "biryani in Madhapur"}]
TOOLS = [{"type": "function", "function": {
    "name": "search_restaurants", "description": "Find restaurants",
    "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "area": {"type": "string"}},
                   "required": ["query"]}}}]


USAGE = {"promptTokenCount": 7, "candidatesTokenCount": 0, "totalTokenCount": 7}


def gemini_text(text="Hello from Gemini"):
    return 200, {"candidates": [{"content": {"parts": [{"text": text}], "role": "model"}, "finishReason": "STOP",
                                 "index": 0}],
                 "usageMetadata": {"promptTokenCount": 7, "candidatesTokenCount": 4, "totalTokenCount": 11}}


def gemini_tool_call():
    return 200, {"candidates": [{"content": {"role": "model", "parts": [
        {"functionCall": {"name": "search_restaurants", "args": {"query": "biryani", "area": "Madhapur"}},
         "thoughtSignature": "c2lnbmF0dXJl"}]}, "finishReason": "STOP", "index": 0}],
        "usageMetadata": {"promptTokenCount": 30, "candidatesTokenCount": 9, "totalTokenCount": 39}}


def groq_text(text="Hello from Groq"):
    return 200, {"id": "chatcmpl-1", "object": "chat.completion", "created": 1, "model": "openai/gpt-oss-120b",
                 "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
                 "usage": {"prompt_tokens": 7, "completion_tokens": 4, "total_tokens": 11},
                 # Groq's real responses carry these; LiteLLM 1.103.1 crashes on a Groq reply without service_tier
                 # (getattr with no default), which the live check in D-032 confirmed Groq does send.
                 "service_tier": "on_demand", "system_fingerprint": "fp_test", "x_groq": {"id": "req_test"}}


def error(status, message="error", code=None):
    return status, {"error": {"code": code or status, "message": message, "status": "ERROR"}}


class FakeProviders:
    """Both providers on one port. `script[provider]` is a list of (status, body[, delay_s]) used in order."""

    def __init__(self):
        self.script = {"gemini": [], "groq": []}
        self.hits = {"gemini": [], "groq": []}
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                provider = "gemini" if ":generateContent" in self.path else "groq"
                body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))) or b"{}")
                fake.hits[provider].append({"path": self.path, "headers": dict(self.headers), "body": body})
                status, payload, *delay = fake.script[provider].pop(0) if fake.script[provider] else error(500)
                if delay:
                    time.sleep(delay[0])
                data = json.dumps(payload).encode()
                try:
                    self.send_response(status)
                    self.send_header("content-type", "application/json")
                    self.send_header("content-length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except OSError:            # the client gave up (timeout test)
                    pass

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def models(self, gemini_key=GEMINI_KEY, groq_key=GROQ_KEY):
        return [Model("gemini/gemini-3.5-flash-lite", gemini_key, self.base + "/v1beta"),
                Model("groq/openai/gpt-oss-120b", groq_key, self.base + "/openai/v1")]

    def counts(self):
        return len(self.hits["gemini"]), len(self.hits["groq"])


@pytest.fixture
def fake():
    f = FakeProviders()
    yield f
    f.server.shutdown()
    f.server.server_close()


# ─── the happy path ──────────────────────────────────────────────────────────────────────────────────────

def test_the_primary_answers_and_the_fallback_is_never_called(fake):
    fake.script["gemini"] = [gemini_text()]
    out = chat(HELLO, models=fake.models())
    assert out["message"] == {"content": "Hello from Gemini", "tool_calls": []}
    assert out["model"] == "gemini/gemini-3.5-flash-lite" and fake.counts() == (1, 0)
    assert [a["outcome"] for a in out["attempts"]] == ["ok"]
    assert out["usage"] == {"prompt_tokens": 7, "completion_tokens": 4}


def test_a_tool_call_comes_back_as_name_and_json_arguments(fake):
    fake.script["gemini"] = [gemini_tool_call()]
    out = chat(HELLO, TOOLS, models=fake.models())
    [call] = out["message"]["tool_calls"]
    assert call["name"] == "search_restaurants" and json.loads(call["arguments"]) == {"query": "biryani",
                                                                                      "area": "Madhapur"}
    assert out["message"]["content"] is None and call["id"]
    sent = fake.hits["gemini"][0]["body"]
    assert sent["tools"][0]["function_declarations"][0]["name"] == "search_restaurants"
    # The whole assistant message is kept for the next request (Gemini 3 needs its thought signature back).
    assert out["raw_message"]["tool_calls"][0]["function"]["name"] == "search_restaurants"


def test_every_request_has_a_token_cap_and_the_key_only_in_a_header(fake):
    fake.script["gemini"] = [error(503)]
    fake.script["groq"] = [groq_text()]
    chat(HELLO, models=fake.models())
    gem, groq = fake.hits["gemini"][0], fake.hits["groq"][0]
    assert gem["body"]["generationConfig"]["max_output_tokens"] == llm.MAX_OUTPUT_TOKENS
    assert groq["body"].get("max_tokens", groq["body"].get("max_completion_tokens")) == llm.MAX_OUTPUT_TOKENS
    assert gem["headers"]["x-goog-api-key"] == GEMINI_KEY and GEMINI_KEY not in gem["path"]
    assert groq["headers"]["Authorization"] == f"Bearer {GROQ_KEY}"


# ─── failures: one request per model, then the fallback, then "busy" ─────────────────────────────────────

@pytest.mark.parametrize("failure, outcome", [
    (error(503, "This model is currently experiencing high demand"), "overloaded"),    # seen live (D-031)
    (error(429, "Resource has been exhausted (e.g. check quota)."), "rate_limited"),
    (error(500, "Internal error encountered."), "provider_error"),
    (error(400, "Invalid JSON payload received."), "bad_request"),
    (error(401, "API key not valid."), "auth"),
    (error(404, "models/gemini-9 is not found"), "model_not_found"),
    ((200, {"candidates": [{"content": {"parts": [], "role": "model"}, "finishReason": "STOP"}],
            "usageMetadata": USAGE}), "empty_reply"),
    ((200, {"candidates": [{"content": {"parts": [{"text": "  "}], "role": "model"}, "finishReason": "STOP"}],
            "usageMetadata": USAGE}), "empty_reply"),
    ((200, {"candidates": [{"finishReason": "MALFORMED_FUNCTION_CALL", "content": {"parts": []}}],
            "usageMetadata": USAGE}), "empty_reply"),
])
def test_any_primary_failure_goes_to_the_fallback_once(fake, failure, outcome):
    fake.script["gemini"] = [failure]
    fake.script["groq"] = [groq_text()]
    out = chat(HELLO, models=fake.models())
    assert out["message"]["content"] == "Hello from Groq" and out["model"] == "groq/openai/gpt-oss-120b"
    assert [a["outcome"] for a in out["attempts"]] == [outcome, "ok"], out["attempts"]
    assert fake.counts() == (1, 1)                                     # no retry anywhere


@pytest.mark.parametrize("groq_failure", [error(429, "Rate limit reached for model"), error(503), error(500)])
def test_both_failing_is_busy_after_exactly_one_request_each(fake, groq_failure):
    fake.script["gemini"] = [error(503, "This model is currently experiencing high demand")]
    fake.script["groq"] = [groq_failure]
    with pytest.raises(LLMUnavailable) as caught:
        chat(HELLO, models=fake.models())
    assert caught.value.user_message == BUSY_MESSAGE == "Dawat AI is busy right now. Please try again in a minute."
    assert [a["outcome"] for a in caught.value.attempts][0] == "overloaded"
    assert fake.counts() == (1, 1)


def test_no_retries_even_if_litellm_is_told_to_retry(fake, monkeypatch):
    # With its defaults, LiteLLM 1.103.1 doesn't retry these providers (planted bug 1 of D-032 changed nothing),
    # so prove our explicit max_retries=0 wins over a global retry setting or a future default.
    import litellm
    monkeypatch.setattr(litellm, "num_retries", 2)
    fake.script["gemini"] = [error(503), error(503), error(503)]
    fake.script["groq"] = [error(429), error(429), error(429)]
    with pytest.raises(LLMUnavailable):
        chat(HELLO, models=fake.models())
    assert fake.counts() == (1, 1)


def test_a_slow_primary_times_out_and_the_fallback_answers(fake, monkeypatch):
    monkeypatch.setattr(llm, "TIMEOUT_SECONDS", 1)
    fake.script["gemini"] = [(*gemini_text(), 3)]                      # answers after 3 s: too late
    fake.script["groq"] = [groq_text()]
    started = time.perf_counter()
    out = chat(HELLO, models=fake.models())
    assert out["attempts"][0]["outcome"] == "timeout" and out["model"].startswith("groq/")
    assert time.perf_counter() - started < 3                           # didn't wait for the slow answer
    assert fake.counts() == (1, 1)


def test_an_unreachable_provider_is_a_connection_failure(fake):
    import socket
    with socket.socket() as s:                                         # a port nothing listens on
        s.bind(("127.0.0.1", 0))
        dead = f"http://127.0.0.1:{s.getsockname()[1]}"
    fake.script["groq"] = [groq_text()]
    models = [Model("gemini/gemini-3.5-flash-lite", GEMINI_KEY, dead + "/v1beta"), fake.models()[1]]
    out = chat(HELLO, models=models)
    assert out["attempts"][0]["outcome"] == "connection" and out["model"].startswith("groq/")


def test_a_model_without_a_key_is_skipped_without_a_request(fake, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    fake.script["groq"] = [groq_text()]
    models = [Model("gemini/gemini-3.5-flash-lite", None, fake.base + "/v1beta"), fake.models()[1]]
    out = chat(HELLO, models=models)
    assert out["attempts"][0]["outcome"] == "not_configured" and fake.counts() == (0, 1)


def test_no_keys_at_all_is_busy_with_no_requests(fake, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GROQ_API_KEY", "  ")                           # blank in .env means not set
    with pytest.raises(LLMUnavailable) as caught:
        chat(HELLO, models=[Model("gemini/gemini-3.5-flash-lite", None, fake.base + "/v1beta"),
                            Model("groq/openai/gpt-oss-120b", None, fake.base + "/openai/v1")])
    assert [a["outcome"] for a in caught.value.attempts] == ["not_configured", "not_configured"]
    assert fake.counts() == (0, 0)


# ─── secrets never reach the attempts log ────────────────────────────────────────────────────────────────

def test_a_provider_echoing_the_key_is_scrubbed(fake):
    fake.script["gemini"] = [error(400, f"API key not valid: {GEMINI_KEY} (url ?key={GEMINI_KEY}&alt=json)")]
    fake.script["groq"] = [error(401, f"Invalid API Key Bearer {GROQ_KEY}")]
    with pytest.raises(LLMUnavailable) as caught:
        chat(HELLO, models=fake.models())
    logged = json.dumps(caught.value.attempts)
    assert GEMINI_KEY not in logged and GROQ_KEY not in logged and "[REDACTED]" in logged


def test_scrub_removes_key_shaped_strings_and_env_keys(monkeypatch):
    google = "AIza" + "B" * 35                                         # built here: never a literal in a file
    groq = "gsk_" + "c" * 40
    monkeypatch.setenv("GEMINI_API_KEY", "env-secret-value-42")
    text = scrub(f"bad {google} and {groq}, GET /v1beta/models?key=abc123&x=1, Bearer xyz.789, env-secret-value-42")
    for secret in (google, groq, "abc123", "xyz.789", "env-secret-value-42"):
        assert secret not in text, secret
    assert text.count("[REDACTED]") == 5 and "&x=1" in text


def test_errors_kept_are_short(fake):
    fake.script["gemini"] = [error(400, "x" * 5000)]
    fake.script["groq"] = [groq_text()]
    out = chat(HELLO, models=fake.models())
    assert len(out["attempts"][0]["error"]) <= llm.MAX_ERROR_CHARS


# ─── configuration ───────────────────────────────────────────────────────────────────────────────────────

def test_the_default_models_come_from_config(monkeypatch):
    assert (config.DEFAULT_LLM_PRIMARY_MODEL, config.DEFAULT_LLM_FALLBACK_MODEL, config.DEFAULT_LLM_FALLBACK_2_MODEL) == (
        "gemini/gemini-3.5-flash-lite", "gemini/gemini-3.8-flash", "groq/openai/gpt-oss-120b")   # D-031, D-036
    monkeypatch.setattr(config, "LLM_PRIMARY_MODEL", "groq/llama-x")
    monkeypatch.setattr(config, "LLM_FALLBACK_MODEL", "gemini/a")
    monkeypatch.setattr(config, "LLM_FALLBACK_2_MODEL", "gemini/b")
    assert [m.name for m in llm.default_models()] == ["groq/llama-x", "gemini/a", "gemini/b"]


def test_the_chain_tries_each_model_once_in_order(fake):
    fake.script["gemini"] = [error(429, "quota"), error(503, "high demand")]
    fake.script["groq"] = [groq_text("from the last resort")]
    models = [fake.models()[0], Model("gemini/gemini-3.8-flash", GEMINI_KEY, fake.base + "/v1beta"), fake.models()[1]]
    out = chat(HELLO, models=models)
    assert out["message"]["content"] == "from the last resort"
    assert [a["outcome"] for a in out["attempts"]] == ["rate_limited", "overloaded", "ok"] and fake.counts() == (2, 1)
    assert [h["path"].split("/")[-1] for h in fake.hits["gemini"]] == [
        "gemini-3.5-flash-lite:generateContent", "gemini-3.8-flash:generateContent"]
    assert fake.hits["gemini"][1]["body"]["generationConfig"]["thinkingConfig"]["thinkingLevel"] == "low"
    assert "thinkingConfig" not in fake.hits["gemini"][0]["body"].get("generationConfig", {})   # Flash-Lite: default


def test_blank_model_settings_mean_the_defaults(monkeypatch):
    import importlib
    monkeypatch.setenv("LLM_PRIMARY_MODEL", "")
    monkeypatch.setenv("LLM_FALLBACK_MODEL", "   ")
    try:
        importlib.reload(config)
        assert config.LLM_PRIMARY_MODEL == "gemini/gemini-3.5-flash-lite"
        assert config.LLM_FALLBACK_MODEL == "gemini/gemini-3.8-flash"
        assert config.LLM_FALLBACK_2_MODEL == "groq/openai/gpt-oss-120b"
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_litellm_does_not_download_anything_on_import():
    assert os.environ.get("LITELLM_LOCAL_MODEL_COST_MAP") == "True"
    import litellm
    assert litellm.turn_off_message_logging is True and litellm.suppress_debug_info is True


def test_a_gemini_message_is_trimmed_for_groq_but_sent_whole_to_gemini(fake):
    # Seen live in 6c: Groq refused a Gemini tool-call message ("property 'images' is unsupported").
    gemini_said = {"role": "assistant", "content": None, "function_call": None, "images": [], "thinking_blocks": [],
                   "provider_specific_fields": {"thought_signatures": ["c2ln"]},
                   "tool_calls": [{"id": "call_1", "type": "function", "index": 0,
                                   "function": {"name": "search_dishes", "arguments": '{"query": "biryani"}'}}]}
    history = [*HELLO, gemini_said, {"role": "tool", "tool_call_id": "call_1", "name": "search_dishes",
                                     "content": '{"status":"ok"}'}]
    fake.script["gemini"] = [error(503)]
    fake.script["groq"] = [groq_text("Here you go")]
    assert chat(history, TOOLS, models=fake.models())["message"]["content"] == "Here you go"
    sent = fake.hits["groq"][0]["body"]["messages"]
    assistant = next(m for m in sent if m["role"] == "assistant")
    assert set(assistant) <= {"role", "content", "tool_calls"}
    assert assistant["tool_calls"] == [{"id": "call_1", "type": "function",
                                        "function": {"name": "search_dishes", "arguments": '{"query": "biryani"}'}}]
    assert llm.for_provider(history, "gemini") is history                # Gemini keeps its thought signatures
