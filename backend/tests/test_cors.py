import pytest
from fastapi.testclient import TestClient

from app.config import parse_allowed_origins, resolve_allowed_origins
from app.main import app

client = TestClient(app)


# --- parsing ---------------------------------------------------------------

def test_parses_comma_separated_list_and_strips_spaces_and_trailing_slash():
    raw = " http://localhost:3000 , https://dawat.vercel.app/ "
    assert parse_allowed_origins(raw) == ["http://localhost:3000", "https://dawat.vercel.app"]


def test_ignores_empty_entries():
    assert parse_allowed_origins("http://localhost:3000,,") == ["http://localhost:3000"]


@pytest.mark.parametrize("raw", ["*", "http://localhost:3000,*"])
def test_wildcard_is_refused(raw):
    with pytest.raises(ValueError, match=r"'\*' is not allowed"):
        parse_allowed_origins(raw)


def test_empty_value_is_refused():
    with pytest.raises(ValueError, match="empty"):
        parse_allowed_origins(" , ")


@pytest.mark.parametrize("env_value", [None, "", "   "])
def test_unset_or_blank_env_falls_back_to_localhost(env_value):
    assert resolve_allowed_origins(env_value) == ["http://localhost:3000"]


def test_set_env_overrides_default():
    assert resolve_allowed_origins("https://dawat.vercel.app") == ["https://dawat.vercel.app"]


# --- behaviour of the running app (default origin: http://localhost:3000) --

def test_allowed_origin_gets_cors_header():
    response = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_unknown_origin_gets_no_cors_header():
    response = client.get("/health", headers={"Origin": "https://evil.example.com"})
    assert "access-control-allow-origin" not in response.headers


def test_preflight_from_unknown_origin_is_rejected():
    response = client.options(
        "/health",
        headers={"Origin": "https://evil.example.com", "Access-Control-Request-Method": "POST"},
    )
    assert response.status_code == 400
