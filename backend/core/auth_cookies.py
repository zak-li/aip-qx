"""Helpers for the cookie-based JWT auth flow.

We migrate JWT from `localStorage` (vulnerable to any XSS) to httpOnly
cookies + CSRF double-submit:

  * Login sets two cookies:
      - `rwa_session`  — JWT, httpOnly, Secure, SameSite=Lax  (auth)
      - `rwa_csrf`     — random hex,  Secure, SameSite=Lax    (readable by JS)

  * The middleware accepts the JWT from either source for now:
      1. `Authorization: Bearer ...` header (legacy clients)
      2. `rwa_session` cookie + matching `X-CSRF-Token` header

    Mutating verbs (POST/PUT/PATCH/DELETE) coming from the cookie path MUST
    include the CSRF header equal to the `rwa_csrf` cookie value. GETs are
    allowed without the header to keep static fetches simple.

  * Logout clears both cookies and blacklists the JWT.
"""
from __future__ import annotations

import secrets

from fastapi import Response

from backend.config import settings

SESSION_COOKIE = "rwa_session"
CSRF_COOKIE = "rwa_csrf"
CSRF_HEADER = "X-CSRF-Token"

# Cookie attributes — Secure forced in production, relaxed in dev so the
# browser does not drop them over plain http://localhost.
_IS_PROD = settings.environment == "production"


def issue_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def set_session_cookies(response: Response, jwt: str, csrf_token: str, max_age_seconds: int) -> None:
    """Attach the JWT and CSRF cookies to a response."""
    response.set_cookie(
        key=SESSION_COOKIE,
        value=jwt,
        max_age=max_age_seconds,
        httponly=True,
        secure=_IS_PROD,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        key=CSRF_COOKIE,
        value=csrf_token,
        max_age=max_age_seconds,
        httponly=False,         # readable by frontend so it can echo the value
        secure=_IS_PROD,
        samesite="lax",
        path="/",
    )


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
