"""Cookie helpers for the Keycloak OIDC session.

Three cookies are managed:
  rwa_session  — Keycloak access token  (httpOnly, Secure, SameSite=Lax)
  rwa_refresh  — Keycloak refresh token (httpOnly, Secure, SameSite=Lax, longer TTL)
  rwa_csrf     — CSRF double-submit token (readable by JS, same TTL as access token)

Mutating requests from cookie-based clients MUST include the X-CSRF-Token header
equal to the rwa_csrf cookie value. GET/HEAD/OPTIONS are exempt.
"""
from __future__ import annotations

import secrets

from fastapi import Response

from core.config import settings

SESSION_COOKIE = "rwa_session"
REFRESH_COOKIE = "rwa_refresh"
CSRF_COOKIE = "rwa_csrf"
CSRF_HEADER = "X-CSRF-Token"

_IS_PROD = settings.environment == "production"

# Keycloak refresh tokens are valid for up to 30 days (configured on realm).
_REFRESH_MAX_AGE = 86400 * 30


def issue_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def set_session_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
    csrf_token: str,
    access_max_age: int,
) -> None:
    """Attach access, refresh, and CSRF cookies to a response."""
    _set_httponly(response, SESSION_COOKIE, access_token, access_max_age)
    _set_httponly(response, REFRESH_COOKIE, refresh_token, _REFRESH_MAX_AGE)
    response.set_cookie(
        key=CSRF_COOKIE,
        value=csrf_token,
        max_age=access_max_age,
        httponly=False,       # must be readable by frontend JS
        secure=_IS_PROD,
        samesite="lax",
        path="/",
    )


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


def _set_httponly(response: Response, name: str, value: str, max_age: int) -> None:
    response.set_cookie(
        key=name,
        value=value,
        max_age=max_age,
        httponly=True,
        secure=_IS_PROD,
        samesite="lax",
        path="/",
    )
