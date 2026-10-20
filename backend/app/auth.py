"""Who is calling? Verifies a Supabase login token and returns the user id (D-022).

THE RULE: a user id comes from exactly one place, the `sub` claim of a token whose signature, issuer,
audience, expiry and role this module has checked. Never from a request body, a query string, a
header other than Authorization, or anything the LLM produces. Every tool that touches user data takes
the id from here.

Supabase signs tokens with the project's private key (ES256 for this project, checked against its JWKS
on 2026-09-30). The backend only ever sees the PUBLIC keys, fetched from
    <SUPABASE_URL>/auth/v1/.well-known/jwks.json
so no signing secret is stored anywhere.
"""

import json
import logging
import threading
import time
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any, Callable

import jwt
from fastapi import Depends, HTTPException, Request

from app import config

log = logging.getLogger("dawat.auth")

# Only the asymmetric algorithm the project actually uses. "none" and HS256 are never accepted, which
# closes the classic attacks (an unsigned token, or an HS256 token "signed" with the public key).
ALGORITHMS = ["ES256"]
AUDIENCE = "authenticated"
LEEWAY_S = 30                     # tolerated clock skew between Supabase and this server
JWKS_LIFESPAN_S = 3600            # re-fetch the public keys at least hourly (key rotation)
JWKS_MIN_REFRESH_S = 60           # an unknown key id triggers at most one re-fetch per minute


class AuthError(Exception):
    """The token is missing, malformed, forged, expired or not for us → 401."""


class AuthUnavailable(Exception):
    """We could not check the token (keys unreachable, not configured) → 503, not the user's fault."""


@dataclass(frozen=True)
class AuthUser:
    user_id: uuid.UUID
    display_name: str | None      # from the token's user_metadata (Google's account name), if there is one


class JwksKeys:
    """Public signing keys by key id, cached. An unknown key id can force a refresh, but only once per
    JWKS_MIN_REFRESH_S, so random key ids in forged tokens can't make us hammer Supabase."""

    def __init__(self, url: str, fetch: Callable[[str], dict] | None = None, clock: Callable[[], float] = time.monotonic):
        self.url, self._fetch, self._clock = url, fetch or _http_get_json, clock
        self._keys: dict[str, Any] = {}
        self._fetched_at: float | None = None
        self._lock = threading.Lock()

    def _refresh(self) -> None:
        try:
            jwks = self._fetch(self.url)
            keys = {k.key_id: k.key for k in jwt.PyJWKSet.from_dict(jwks).keys if k.key_id}
        except Exception as e:                       # network, bad JSON, no usable keys
            raise AuthUnavailable(f"could not load signing keys: {type(e).__name__}") from e
        self._keys, self._fetched_at = keys, self._clock()

    def get(self, kid: str) -> Any:
        with self._lock:
            now = self._clock()
            stale = self._fetched_at is None or now - self._fetched_at > JWKS_LIFESPAN_S
            may_refresh = self._fetched_at is None or now - self._fetched_at > JWKS_MIN_REFRESH_S
            if stale or (kid not in self._keys and may_refresh):
                self._refresh()
            if kid not in self._keys:
                raise AuthError("unknown signing key")
            return self._keys[kid]


def _http_get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())


class TokenVerifier:
    def __init__(self, issuer: str, key_for_kid: Callable[[str], Any]):
        self.issuer, self._key_for_kid = issuer, key_for_kid

    def verify(self, token: str) -> AuthUser:
        # Check the header before any key lookup, so a token for another algorithm never reaches the keys.
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as e:
            raise AuthError("malformed token") from e
        if header.get("alg") not in ALGORITHMS or not isinstance(header.get("kid"), str):
            raise AuthError("unexpected token algorithm or no key id")
        key = self._key_for_kid(header["kid"])
        try:
            claims = jwt.decode(token, key, algorithms=ALGORITHMS, audience=AUDIENCE, issuer=self.issuer,
                                leeway=LEEWAY_S, options={"require": ["exp", "iat", "sub", "aud", "iss"]})
        except jwt.PyJWTError as e:
            raise AuthError(type(e).__name__) from e

        # Supabase puts "authenticated" in role for signed-in users; anon/service tokens are not users.
        if claims.get("role") != "authenticated":
            raise AuthError("not a user token")
        # Google is the only sign-in (D-064). The anonymous sign-ins D-048 accepted for the demo accounts are refused
        # again, so turning them off in Supabase isn't the only thing standing between a guest and the site.
        if claims.get("is_anonymous") not in (None, False):
            raise AuthError("anonymous sign-ins are not accepted")
        try:
            user_id = uuid.UUID(str(claims["sub"]))
        except ValueError as e:
            raise AuthError("subject is not a user id") from e
        meta = claims.get("user_metadata") if isinstance(claims.get("user_metadata"), dict) else {}
        name = meta.get("display_name") or meta.get("full_name")
        display_name = (name.strip()[:60] or None) if isinstance(name, str) else None
        return AuthUser(user_id=user_id, display_name=display_name)


_verifier: TokenVerifier | None = None
_verifier_lock = threading.Lock()


def get_verifier() -> TokenVerifier:
    """FastAPI dependency; tests override it with a verifier that trusts a test key."""
    global _verifier
    if _verifier is None:
        # D-059: the local dev login replaces Supabase's keys only when app.devauth says it is enabled, which needs
        # the launcher's flag AND a database on this machine AND no hosting platform (it raises otherwise).
        from app import devauth
        if devauth.enabled():
            with _verifier_lock:
                if _verifier is None:
                    _verifier = devauth.verifier()
            return _verifier
        if not config.SUPABASE_URL:
            raise HTTPException(503, "Sign-in is not configured on this server.")
        with _verifier_lock:
            if _verifier is None:
                issuer = f"{config.SUPABASE_URL}/auth/v1"
                _verifier = TokenVerifier(issuer, JwksKeys(f"{issuer}/.well-known/jwks.json").get)
    return _verifier


_UNAUTHORISED = {"WWW-Authenticate": "Bearer"}


def require_user(request: Request, verifier: TokenVerifier = Depends(get_verifier)) -> AuthUser:
    """The ONLY way a route learns who the user is. The reason for a rejection is logged, never returned:
    telling a caller *why* a forged token failed only helps them fix it."""
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(401, "Please sign in to continue.", headers=_UNAUTHORISED)
    try:
        return verifier.verify(token.strip())
    except AuthUnavailable as e:
        log.warning("token check unavailable: %s", e)
        raise HTTPException(503, "Sign-in check is temporarily unavailable. Please try again.") from None
    except AuthError as e:
        log.info("token rejected: %s", e)
        raise HTTPException(401, "Your session is invalid or has expired. Please sign in again.",
                            headers=_UNAUTHORISED) from None


def optional_user(request: Request, verifier: TokenVerifier = Depends(get_verifier)) -> AuthUser | None:
    """For public routes that do better with a user (POST /plans prices from their delivery address): no
    Authorization header → anonymous (None). A header that is present is checked exactly like require_user, so a
    bad or forged token is a 401, never a silent fall-back to anonymous."""
    if "authorization" not in request.headers:
        return None
    return require_user(request, verifier)
