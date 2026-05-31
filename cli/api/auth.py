"""
cli/api/auth.py
---------------
Authentication clients — both flows are supported:

  1. Direct Access Grant (resource owner password) — kept for backwards
     compatibility but discouraged by OAuth 2.0 Security BCP.
  2. Authorization Code + PKCE — preferred. Pops a browser to Keycloak,
     intercepts the redirect on a localhost loopback, exchanges code → tokens.

API endpoints (prefix /api/v1/auth):
  GET    /login         (server-side redirect helper)
  GET    /callback      (server-side code exchange)
  POST   /logout
  POST   /refresh
  GET    /me
  GET    /me/export     (GDPR data export)
  DELETE /me            (GDPR account deletion)
"""
from __future__ import annotations

import http.server
import logging
import socket
import threading
import webbrowser
from typing import Any
from urllib.parse import parse_qs, urlparse

from cli.http import request
from cli.security.pkce import (
    build_authorization_url,
    generate_pkce_pair,
    generate_state,
)
from cli.security.tokens import (
    TokenBundle,
    delete_tokens,
    get_token_bundle,
    save_token_bundle,
)
from cli.settings import settings

log = logging.getLogger(__name__)


def _kc_token_url() -> str:
    return (
        f"{settings.keycloak_url.rstrip('/')}"
        f"/realms/{settings.keycloak_realm}"
        f"/protocol/openid-connect/token"
    )


# ── Direct Access Grant (legacy fallback) ───────────────────────────────────


async def login_password(username: str, password: str) -> TokenBundle:
    """
    Resource Owner Password Credentials flow.

    Less secure than PKCE — the CLI sees the user's password — but useful
    for non-interactive contexts (CI smoke tests). Kept gated behind an
    explicit flag in commands/auth.py.
    """
    data = {
        "grant_type": "password",
        "client_id": settings.keycloak_client_id,
        "username": username,
        "password": password,
        "scope": "openid profile email",
    }
    if settings.is_confidential_client and settings.keycloak_client_secret:
        data["client_secret"] = settings.keycloak_client_secret

    response = await request("POST", _kc_token_url(), data=data, skip_auth=True)
    bundle = TokenBundle.from_oidc_response(response.json())
    save_token_bundle(bundle)
    log.info("Password-grant login successful for %s", username)
    return bundle


# ── Authorization Code + PKCE (recommended) ─────────────────────────────────


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """Single-shot loopback handler: captures `?code=` then signals the parent."""

    received_query: dict[str, list[str]] = {}
    done: threading.Event = threading.Event()

    def do_GET(self):
        parsed = urlparse(self.path)
        _CallbackHandler.received_query = parse_qs(parsed.query)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            "<html><body style='font-family:system-ui;text-align:center;"
            "padding:3rem'><h2>Pxtly CLI</h2>"
            "<p>Authentication complete — you can close this tab.</p>"
            "</body></html>".encode()
        )
        _CallbackHandler.done.set()

    def log_message(self, *_args):  # silence the default stderr noise
        return


async def login_pkce(open_browser: bool = True, timeout: float = 180.0) -> TokenBundle:
    """
    Run the full Authorization Code + PKCE dance.

    Spawns a loopback HTTP server on a random port, opens the browser to the
    Keycloak `/auth` endpoint, waits for the redirect, then POSTs the code
    to `/token` with the PKCE verifier.
    """
    port = _free_port()
    redirect_uri = f"http://127.0.0.1:{port}/callback"
    verifier, challenge = generate_pkce_pair()
    state = generate_state()

    url = build_authorization_url(
        keycloak_url=settings.keycloak_url,
        realm=settings.keycloak_realm,
        client_id=settings.keycloak_client_id,
        redirect_uri=redirect_uri,
        code_challenge=challenge,
        state=state,
    )

    # Reset handler state in case this is the second run in the same process.
    _CallbackHandler.received_query = {}
    _CallbackHandler.done = threading.Event()

    server = http.server.HTTPServer(("127.0.0.1", port), _CallbackHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    log.info("PKCE flow: redirect_uri=%s", redirect_uri)
    if open_browser:
        webbrowser.open(url)
    else:
        print(f"Open this URL in a browser:\n  {url}")

    try:
        if not _CallbackHandler.done.wait(timeout=timeout):
            raise TimeoutError(
                f"PKCE flow timed out after {timeout:.0f}s waiting for the "
                f"browser redirect."
            )
    finally:
        server.shutdown()
        server.server_close()

    qs = _CallbackHandler.received_query
    if "error" in qs:
        raise RuntimeError(f"Keycloak refused the request: {qs['error'][0]}")
    if qs.get("state", [""])[0] != state:
        raise RuntimeError("State mismatch — possible CSRF, refusing tokens.")
    code = qs.get("code", [""])[0]
    if not code:
        raise RuntimeError("No `code` returned by Keycloak.")

    data = {
        "grant_type": "authorization_code",
        "client_id": settings.keycloak_client_id,
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": verifier,
    }
    if settings.is_confidential_client and settings.keycloak_client_secret:
        data["client_secret"] = settings.keycloak_client_secret

    response = await request("POST", _kc_token_url(), data=data, skip_auth=True)
    bundle = TokenBundle.from_oidc_response(response.json())
    save_token_bundle(bundle)
    log.info("PKCE login successful.")
    return bundle


# ── Refresh / logout / profile ──────────────────────────────────────────────


async def refresh_now() -> TokenBundle | None:
    """
    Force a refresh of the current token bundle. Returns the new bundle, or
    None if there is no refresh token or it has expired.
    """
    bundle = get_token_bundle()
    if not bundle or not bundle.refresh_token or bundle.is_refresh_expired():
        return None

    data = {
        "grant_type": "refresh_token",
        "client_id": settings.keycloak_client_id,
        "refresh_token": bundle.refresh_token,
    }
    if settings.is_confidential_client and settings.keycloak_client_secret:
        data["client_secret"] = settings.keycloak_client_secret

    response = await request("POST", _kc_token_url(), data=data, skip_auth=True)
    new_bundle = TokenBundle.from_oidc_response(response.json())
    save_token_bundle(new_bundle)
    return new_bundle


async def logout() -> None:
    """
    Revoke the refresh token on Keycloak's side, then clear local state.
    """
    bundle = get_token_bundle()
    if bundle and bundle.refresh_token:
        url = (
            f"{settings.keycloak_url.rstrip('/')}"
            f"/realms/{settings.keycloak_realm}"
            f"/protocol/openid-connect/logout"
        )
        data = {
            "client_id": settings.keycloak_client_id,
            "refresh_token": bundle.refresh_token,
        }
        if settings.is_confidential_client and settings.keycloak_client_secret:
            data["client_secret"] = settings.keycloak_client_secret
        try:
            await request("POST", url, data=data, skip_auth=True)
        except Exception as exc:
            log.warning("Server-side logout failed: %s", exc)
    delete_tokens()


async def me() -> dict[str, Any]:
    return (await request("GET", f"{settings.api_url}/auth/me")).json()


async def me_export() -> dict[str, Any]:
    """GDPR — download every record the platform holds about the caller."""
    return (await request("GET", f"{settings.api_url}/auth/me/export")).json()


async def me_delete() -> None:
    """GDPR — delete the caller's account (DELETE /auth/me, 204)."""
    await request("DELETE", f"{settings.api_url}/auth/me")
