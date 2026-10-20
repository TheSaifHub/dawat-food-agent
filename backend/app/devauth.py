"""The LOCAL dev login (D-059): sign in to the dev site without Supabase, against the local dawat_dev database.

Saif's rule (Session 20): daily work avoids Supabase (egress), and a dev login must never be switchable on in the
deployed app. Five locks, of which this module holds the backend's three:

  1. Off unless launched for it: only `dev_server.py start` (local mode) sets DAWAT_DEV_LOGIN=1, for that one process.
     If the flag is found in backend/.env, the server refuses, so a copied env file can never carry it.
  2. `enabled()` REFUSES (raises DevLoginRefused) when the flag is set but the database isn't on this machine, or a
     hosting platform's marker variable is present (Render sets RENDER on every service; VERCEL for completeness),
     or the flag has any value other than 1. app/main.py calls it at import, so such a server never starts.
  3. When it's off, nothing of it exists: the /dev/auth routes aren't mounted, and app/auth.py's verifier trusts only
     Supabase's issuer and keys, so a dev token is a 401.
(Locks 4 and 5 are the frontend's production-build guard and the tests.)

When on, the tokens are ES256 and go through the SAME TokenVerifier as Supabase's (signature, issuer, audience, expiry,
role, subject); only the key and the issuer differ. Supabase tokens are refused in this mode: the local database
has no Supabase users anyway.

The private key is generated once into backend/.dev_login/ (gitignored, never printed), so a restart keeps people
signed in. It signs only tokens that a backend on a LOCAL database will accept.
"""

import hashlib
import os
import threading
import time
import uuid
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from dotenv import dotenv_values

from app import config
from app.auth import AUDIENCE, AuthError, TokenVerifier
from app.localdb import ENV_FILE, is_local

FLAG = "DAWAT_DEV_LOGIN"
DEPLOY_MARKERS = ("RENDER", "VERCEL")
ISSUER = "dawat-dev-login"            # never a Supabase issuer (those are https://<project>.supabase.co/auth/v1)
KEY_FILE = Path(__file__).resolve().parents[1] / ".dev_login" / "es256.pem"
TOKEN_LIFETIME_S = 12 * 3600


class DevLoginRefused(RuntimeError):
    """The dev login was asked for somewhere it must not run. The server refuses to start."""


def enabled() -> bool:
    """False when the flag is unset, blank or 0. True only when it is exactly 1 AND the database is on this machine
    AND no hosting platform is detected. Any other combination raises: a misconfiguration is loud, never quiet."""
    raw = os.environ.get(FLAG)
    if raw is None or raw.strip() in ("", "0"):
        return False
    if raw.strip() != "1":
        raise DevLoginRefused(f"{FLAG} must be 1 or unset. Refusing to start.")
    if FLAG in dotenv_values(ENV_FILE):
        raise DevLoginRefused(f"{FLAG} is in the backend's env file. Only the launcher sets it (dev_server.py start), "
                              "so a copied env file can never turn it on. Remove the line. Refusing to start.")
    found = [m for m in DEPLOY_MARKERS if m in os.environ]
    if found:
        raise DevLoginRefused(f"{FLAG} is set on a hosting platform ({', '.join(found)}). The dev login never runs "
                              "in a deployed app. Refusing to start.")
    if not is_local(config.DATABASE_URL):
        raise DevLoginRefused(f"{FLAG} is set but the database isn't on this machine. The dev login only runs against "
                              "the local dev database (dev_server.py start). Refusing to start.")
    return True


_key: ec.EllipticCurvePrivateKey | None = None
_key_lock = threading.Lock()


def _private_key() -> ec.EllipticCurvePrivateKey:
    global _key
    with _key_lock:
        if _key is None:
            if KEY_FILE.exists():
                _key = serialization.load_pem_private_key(KEY_FILE.read_bytes(), password=None)
            else:
                _key = ec.generate_private_key(ec.SECP256R1())
                KEY_FILE.parent.mkdir(exist_ok=True)
                KEY_FILE.write_bytes(_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                        serialization.NoEncryption()))
                try:
                    os.chmod(KEY_FILE, 0o600)
                except OSError:
                    pass
        return _key


def _public_key():
    return _private_key().public_key()


def key_id() -> str:
    der = _public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return "dawat-dev-" + hashlib.sha256(der).hexdigest()[:16]


def _key_for_kid(kid: str):
    if kid != key_id():
        raise AuthError("unknown signing key")
    return _public_key()


def verifier() -> TokenVerifier:
    """The dev mode's verifier: the same checks as Supabase's, with the dev issuer and key. Refuses to exist when the
    dev login isn't enabled (a second check behind app/auth.py's)."""
    if not enabled():
        raise DevLoginRefused("The dev login isn't enabled.")
    return TokenVerifier(ISSUER, _key_for_kid)


def issue_token(user_id: uuid.UUID, *, display_name: str | None = None, email: str | None = None) -> dict:
    """A Supabase-shaped access token for a user that exists in the local auth.users."""
    if not enabled():
        raise DevLoginRefused("The dev login isn't enabled.")
    now = int(time.time())
    claims = {"iss": ISSUER, "aud": AUDIENCE, "sub": str(user_id), "role": "authenticated", "iat": now,
              "exp": now + TOKEN_LIFETIME_S, "is_anonymous": False,
              "user_metadata": {"full_name": display_name} if display_name else {}}
    if email:
        claims["email"] = email
    token = jwt.encode(claims, _private_key(), algorithm="ES256", headers={"kid": key_id()})
    return {"access_token": token, "expires_at": claims["exp"], "user_id": str(user_id)}
