"""
cli/security/pkce.py
--------------------
OAuth 2.0 Authorization Code + PKCE helpers (RFC 7636).

The CLI uses this for `pxtly auth login --pkce`: rather than asking the
user for their password and posting it via Direct Access Grant
(grant_type=password, which is officially discouraged by the OAuth 2.0
Security Best Current Practice), it pops a browser to the Keycloak
authorisation endpoint with a PKCE challenge, intercepts the redirect
on a localhost loopback, then exchanges the code for tokens.

This file only provides the pure primitives — the loopback HTTP server
and browser orchestration live in cli/api/auth.py.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
from urllib.parse import urlencode

_CODE_VERIFIER_LEN = 64  # RFC 7636 §4.1: 43–128 chars after base64url
_STATE_LEN = 32


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def generate_pkce_pair() -> tuple[str, str]:
    """
    Return (code_verifier, code_challenge) for a single auth attempt.

    The verifier is a high-entropy random string; the challenge is the
    SHA-256 of the verifier, base64url-encoded without padding (S256 method
    — the only method this CLI advertises).
    """
    verifier_bytes = secrets.token_bytes(_CODE_VERIFIER_LEN)
    verifier = _b64url(verifier_bytes)
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def generate_state() -> str:
    """Return a random `state` value for CSRF protection on the redirect."""
    return _b64url(secrets.token_bytes(_STATE_LEN))


def build_authorization_url(
    *,
    keycloak_url: str,
    realm: str,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    state: str,
    scope: str = "openid profile email",
) -> str:
    """
    Compose the full authorisation URL for the browser.

    Caller passes the PKCE challenge + state; the verifier stays in memory
    until the token exchange step.
    """
    base = f"{keycloak_url.rstrip('/')}/realms/{realm}/protocol/openid-connect/auth"
    qs = urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{base}?{qs}"
