"""Token verification (app/auth.py, D-022): a valid Supabase-style token yields its user id; every forgery,
mix-up and expired token is refused. No network: tokens are signed with a throwaway test key."""

import base64
import hashlib
import hmac
import json
import time
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives import serialization

from app.auth import AuthError, AuthUnavailable, JwksKeys, TokenVerifier, JWKS_LIFESPAN_S, JWKS_MIN_REFRESH_S
from tests.conftest import DROP, ISSUER, KID

USER_A = uuid.UUID("11111111-1111-4111-8111-111111111111")
USER_B = uuid.UUID("22222222-2222-4222-8222-222222222222")


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def test_valid_token_gives_its_user_id(verifier, make_token):
    user = verifier.verify(make_token(USER_A, user_metadata={"display_name": "  Priya  "}))
    assert user.user_id == USER_A
    assert user.display_name == "Priya"


def test_display_name_is_optional_and_capped(verifier, make_token):
    assert verifier.verify(make_token(USER_A)).display_name is None
    assert verifier.verify(make_token(USER_A, user_metadata={"display_name": "x" * 200})).display_name == "x" * 60
    assert verifier.verify(make_token(USER_A, user_metadata="not a dict")).display_name is None


@pytest.mark.parametrize("label, claims", [
    ("expired beyond the 30 s leeway", {"exp": int(time.time()) - 120}),
    ("wrong audience (anon key token)", {"aud": "anon"}),
    ("another Supabase project", {"iss": "https://other-project.supabase.co/auth/v1"}),
    ("anon role", {"role": "anon"}),
    ("service role", {"role": "service_role"}),
    ("no role", {"role": DROP}),
    ("subject is not a uuid", {"sub": "admin"}),
    ("no subject", {"sub": DROP}),
    ("no expiry", {"exp": DROP}),
    ("no issued-at", {"iat": DROP}),
    ("no issuer", {"iss": DROP}),
    ("not valid yet", {"nbf": int(time.time()) + 3600}),
])
def test_bad_claims_are_refused(verifier, make_token, label, claims):
    with pytest.raises(AuthError):
        verifier.verify(make_token(USER_A, **claims))


@pytest.mark.parametrize("flag", [True, "true", 1, "1"])
def test_anonymous_sign_ins_are_refused(verifier, make_token, flag):
    """D-064: Google is the only sign-in, so the anonymous tokens D-048 accepted are refused, whatever the spelling."""
    with pytest.raises(AuthError):
        verifier.verify(make_token(USER_A, is_anonymous=flag))


@pytest.mark.parametrize("claims", [{}, {"is_anonymous": False}])
def test_a_normal_token_has_no_anonymous_flag_and_is_accepted(verifier, make_token, claims):
    assert verifier.verify(make_token(USER_A, **claims)).user_id == USER_A


def test_expiry_within_leeway_is_accepted(verifier, make_token):
    assert verifier.verify(make_token(USER_A, exp=int(time.time()) - 10)).user_id == USER_A


def test_signed_by_another_key_is_refused(verifier, make_token, attacker_key):
    with pytest.raises(AuthError):
        verifier.verify(make_token(USER_A, key=attacker_key))


def test_tampered_payload_is_refused(verifier, make_token):
    """Take a real token for A and swap in B's user id, keeping A's signature."""
    header, payload, sig = make_token(USER_A).split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=="))
    claims["sub"] = str(USER_B)
    forged = ".".join([header, b64(json.dumps(claims).encode()), sig])
    with pytest.raises(AuthError):
        verifier.verify(forged)


def test_unsigned_alg_none_is_refused(verifier):
    now = int(time.time())
    header = b64(json.dumps({"alg": "none", "typ": "JWT", "kid": KID}).encode())
    payload = b64(json.dumps({"iss": ISSUER, "aud": "authenticated", "role": "authenticated", "sub": str(USER_A),
                              "iat": now, "exp": now + 3600}).encode())
    with pytest.raises(AuthError):
        verifier.verify(f"{header}.{payload}.")


def test_hs256_signed_with_the_public_key_is_refused(verifier, signing_key):
    """Algorithm confusion: the attacker knows the PUBLIC key and uses it as an HMAC secret."""
    pem = signing_key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    now = int(time.time())
    header = b64(json.dumps({"alg": "HS256", "typ": "JWT", "kid": KID}).encode())
    payload = b64(json.dumps({"iss": ISSUER, "aud": "authenticated", "role": "authenticated", "sub": str(USER_A),
                              "iat": now, "exp": now + 3600}).encode())
    sig = b64(hmac.new(pem, f"{header}.{payload}".encode(), hashlib.sha256).digest())
    with pytest.raises(AuthError):
        verifier.verify(f"{header}.{payload}.{sig}")


@pytest.mark.parametrize("token", ["", "abc", "a.b.c", "eyJhbGciOiJFUzI1NiJ9.e30.", "Bearer x"])
def test_garbage_is_refused(verifier, token):
    with pytest.raises(AuthError):
        verifier.verify(token)


def test_other_algorithms_never_reach_the_key_lookup(make_token):
    """A token claiming another algorithm, or with no key id, is refused before any key is fetched."""
    lookups = []
    v = TokenVerifier(ISSUER, lambda kid: lookups.append(kid))
    for token in (make_token(USER_A, key="x" * 32, alg="HS256"), make_token(USER_A, kid=None)):
        with pytest.raises(AuthError):
            v.verify(token)
    assert lookups == []


def test_unknown_key_id_is_refused(verifier, make_token):
    with pytest.raises(AuthError):
        verifier.verify(make_token(USER_A, kid="some-other-key"))


# ─── JwksKeys: caching and refresh limits ──────────────────────────────
class FakeJwks:
    def __init__(self, key, kid=KID):
        jwk = jwt.algorithms.ECAlgorithm.to_jwk(key.public_key(), as_dict=True)
        self.doc = {"keys": [{**jwk, "kid": kid, "alg": "ES256", "use": "sig"}]}
        self.calls, self.fail = 0, False

    def __call__(self, url):
        self.calls += 1
        if self.fail:
            raise OSError("network down")
        return self.doc


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_jwks_is_fetched_once_and_cached(signing_key):
    fake, clock = FakeJwks(signing_key), Clock()
    keys = JwksKeys("https://x/jwks", fetch=fake, clock=clock)
    keys.get(KID)
    keys.get(KID)
    assert fake.calls == 1


def test_unknown_key_ids_cannot_hammer_supabase(signing_key):
    fake, clock = FakeJwks(signing_key), Clock()
    keys = JwksKeys("https://x/jwks", fetch=fake, clock=clock)
    keys.get(KID)
    for i in range(50):
        with pytest.raises(AuthError):
            keys.get(f"random-{i}")
    assert fake.calls == 1                      # no refetch within the minute
    clock.t += JWKS_MIN_REFRESH_S + 1
    with pytest.raises(AuthError):
        keys.get("random-again")
    assert fake.calls == 2                      # one refetch after it


def test_keys_are_refreshed_after_their_lifespan(signing_key):
    fake, clock = FakeJwks(signing_key), Clock()
    keys = JwksKeys("https://x/jwks", fetch=fake, clock=clock)
    keys.get(KID)
    clock.t += JWKS_LIFESPAN_S + 1
    keys.get(KID)
    assert fake.calls == 2


def test_unreachable_jwks_is_unavailable_not_unauthorised(signing_key):
    fake = FakeJwks(signing_key)
    fake.fail = True
    with pytest.raises(AuthUnavailable):
        JwksKeys("https://x/jwks", fetch=fake, clock=Clock()).get(KID)


def test_verifier_with_jwks_end_to_end(signing_key, make_token):
    v = TokenVerifier(ISSUER, JwksKeys("https://x/jwks", fetch=FakeJwks(signing_key), clock=Clock()).get)
    assert v.verify(make_token(USER_A)).user_id == USER_A


@pytest.mark.live
def test_real_supabase_jwks_loads(supabase_url):
    """One real request: the project's public keys parse and include an ES256 signing key."""
    keys = JwksKeys(f"{supabase_url}/auth/v1/.well-known/jwks.json")
    keys._refresh()
    assert keys._keys, "no usable keys in the project's JWKS"
