"""Keycloak OIDC client.

Responsibilities:
  - Cache Keycloak's JWKS (public keys) and validate access tokens locally (RS256).
  - Build PKCE authorization URLs (code_challenge / code_verifier).
  - Exchange authorization codes for token sets.
  - Refresh access tokens.
  - Revoke Keycloak sessions on logout.

Token validation never calls Keycloak on the hot path — it uses the cached JWKS.
On a key-rotation miss the JWKS is refreshed once, then retried.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import secrets
import time
import urllib.parse
from typing import Any

import httpx
from jose import JWTError, jwt

from core.config import settings

logger = logging.getLogger(__name__)

# Valid application roles (must match user_role_enum in DB)
VALID_APP_ROLES: frozenset[str] = frozenset(
    {
        "SUPER_ADMIN",
        "ADMIN_ORG",
        "EMETTEUR",
        "CUSTODIAN",
        "TRADER",
        "REGULATEUR",
        "AUDITEUR",
        "COMPLIANCE_OFFICER",
        "READONLY",
    }
)

# JWKS in-memory cache (per-process; safe under asyncio single-event-loop model)
_jwks_cache: dict[str, Any] | None = None
_jwks_fetched_at: float = 0.0
_JWKS_TTL: float = 3600.0            # refresh at most once per hour
_jwks_lock: asyncio.Lock = asyncio.Lock()


# ──────────────────────────── URL helpers ────────────────────────────────────

def _issuer() -> str:
    return f"{settings.keycloak_url}/realms/{settings.keycloak_realm}"


def _certs_url() -> str:
    return f"{_issuer()}/protocol/openid-connect/certs"


def _token_url() -> str:
    return f"{_issuer()}/protocol/openid-connect/token"


def _auth_url() -> str:
    return f"{_issuer()}/protocol/openid-connect/auth"


def _logout_url() -> str:
    return f"{_issuer()}/protocol/openid-connect/logout"


def _http_client() -> httpx.AsyncClient:
    # A pinned CA path takes precedence over the bool: httpx accepts either a
    # string path (custom trust anchor) or a bool (system store / no verify).
    verify: str | bool = settings.keycloak_ca_cert_path or settings.keycloak_verify_tls
    return httpx.AsyncClient(
        timeout=httpx.Timeout(connect=5.0, read=15.0, write=10.0, pool=5.0),
        verify=verify,
    )


# ──────────────────────────── JWKS cache ─────────────────────────────────────

async def _fetch_jwks(force: bool = False) -> dict[str, Any]:
    """Return the JWKS dict, refreshing the cache when stale or forced."""
    global _jwks_cache, _jwks_fetched_at

    now = time.monotonic()
    if not force and _jwks_cache and (now - _jwks_fetched_at) < _JWKS_TTL:
        return _jwks_cache

    async with _jwks_lock:
        now = time.monotonic()
        if not force and _jwks_cache and (now - _jwks_fetched_at) < _JWKS_TTL:
            return _jwks_cache          # another coroutine refreshed while we waited

        async with _http_client() as client:
            resp = await client.get(_certs_url())
            resp.raise_for_status()

        _jwks_cache = resp.json()
        _jwks_fetched_at = time.monotonic()
        logger.info("Keycloak JWKS cache refreshed (keys=%d)", len(_jwks_cache.get("keys", [])))
        return _jwks_cache


# ──────────────────────────── Token validation ───────────────────────────────

async def validate_token(token: str) -> dict[str, Any]:
    """Validate a Keycloak access token.

    Verifies signature (RS256), expiry, issuer, and audience.
    Returns the decoded payload on success; raises ValueError on any failure.
    """
    jwks = await _fetch_jwks()

    decode_opts = {
        "require": ["exp", "iat", "sub", "iss", "jti"],
        "verify_aud": False,   # checked manually — Keycloak sets aud to client IDs
    }

    try:
        payload = _decode(token, jwks, decode_opts)
    except JWTError:
        # Possible key rotation — refresh JWKS once and retry.
        jwks = await _fetch_jwks(force=True)
        try:
            payload = _decode(token, jwks, decode_opts)
        except JWTError as exc:
            raise ValueError(f"Invalid or expired token: {exc}") from exc

    _check_audience(payload)
    return payload


def _decode(token: str, jwks: dict, options: dict) -> dict[str, Any]:
    return jwt.decode(
        token,
        jwks,
        algorithms=["RS256"],
        issuer=_issuer(),
        options=options,
    )


def _check_audience(payload: dict[str, Any]) -> None:
    """Token must be intended for rwa-api (aud) or issued by it (azp)."""
    aud: str | list[str] = payload.get("aud", [])
    if isinstance(aud, str):
        aud = [aud]
    azp: str = payload.get("azp", "")
    if settings.keycloak_client_id not in aud and azp != settings.keycloak_client_id:
        raise ValueError(
            f"Token audience {aud!r} / azp={azp!r} does not match client_id "
            f"'{settings.keycloak_client_id}'"
        )


# ──────────────────────────── Role extraction ────────────────────────────────

def extract_role(payload: dict[str, Any]) -> str | None:
    """Return the application role from the token payload.

    Checks the custom `rwa_role` claim first (set via Keycloak attribute mapper),
    then falls back to scanning `realm_access.roles`.
    """
    role = payload.get("rwa_role")
    if role and role in VALID_APP_ROLES:
        return role
    for r in payload.get("realm_access", {}).get("roles", []):
        if r in VALID_APP_ROLES:
            return r
    return None


# ──────────────────────────── PKCE helpers ───────────────────────────────────

def generate_pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for S256 PKCE."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def generate_state() -> str:
    return secrets.token_urlsafe(32)


def build_authorization_url(redirect_uri: str, state: str, code_challenge: str) -> str:
    """Build the Keycloak authorization endpoint URL (PKCE, authorization_code flow)."""
    params = {
        "client_id": settings.keycloak_client_id,
        "response_type": "code",
        "scope": "openid email profile",
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{_auth_url()}?{urllib.parse.urlencode(params)}"


# ──────────────────────────── Token lifecycle ────────────────────────────────

async def exchange_code(code: str, redirect_uri: str, code_verifier: str) -> dict[str, Any]:
    """Exchange an authorization code for access + refresh tokens (PKCE)."""
    async with _http_client() as client:
        resp = await client.post(
            _token_url(),
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": settings.keycloak_client_id,
                "client_secret": settings.keycloak_client_secret,
                "code_verifier": code_verifier,
            },
        )
        if resp.status_code != 200:
            logger.error("Keycloak code exchange failed (%s): %s", resp.status_code, resp.text)
            raise ValueError("Authorization code exchange failed.")
        return resp.json()


async def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    """Use a refresh token to obtain a new access token."""
    async with _http_client() as client:
        resp = await client.post(
            _token_url(),
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": settings.keycloak_client_id,
                "client_secret": settings.keycloak_client_secret,
            },
        )
        if resp.status_code != 200:
            logger.warning("Keycloak token refresh failed (%s)", resp.status_code)
            raise ValueError("Token refresh failed — please log in again.")
        return resp.json()


async def revoke_session(refresh_token: str) -> None:
    """Back-channel logout: revoke the Keycloak session tied to the refresh token."""
    async with _http_client() as client:
        resp = await client.post(
            _logout_url(),
            data={
                "client_id": settings.keycloak_client_id,
                "client_secret": settings.keycloak_client_secret,
                "refresh_token": refresh_token,
            },
        )
        if resp.status_code not in (200, 204):
            logger.warning("Keycloak back-channel logout returned %s", resp.status_code)


async def delete_keycloak_user(keycloak_sub: str) -> None:
    """Delete a user from Keycloak (GDPR erasure). Uses the Admin REST API."""
    token = await _get_admin_token()
    async with _http_client() as client:
        resp = await client.delete(
            f"{settings.keycloak_url}/admin/realms/{settings.keycloak_realm}/users/{keycloak_sub}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code not in (200, 204):
            logger.warning("Keycloak user deletion returned %s for sub=%s", resp.status_code, keycloak_sub)


async def _get_admin_token() -> str:
    """Obtain a short-lived admin token using client credentials."""
    async with _http_client() as client:
        resp = await client.post(
            _token_url(),
            data={
                "grant_type": "client_credentials",
                "client_id": settings.keycloak_client_id,
                "client_secret": settings.keycloak_client_secret,
            },
        )
        resp.raise_for_status()
        return resp.json()["access_token"]
