"""Authentication middleware — Keycloak OIDC edition.

Validates the Keycloak access token on every protected request by:
  1. Extracting the JWT from the Authorization: Bearer header or the rwa_session cookie.
  2. Verifying the signature via the cached JWKS (RS256, issuer, audience).
  3. Checking the token's jti against the Redis blacklist (for immediate logout).
  4. Enforcing CSRF double-submit on mutating cookie-based requests.

On success the decoded token payload is stored in request.state.token_payload
and request.state.keycloak_sub is set to payload["sub"] for downstream use.
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from core.core.auth_cookies import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE
from core.core.oidc import validate_token
from core.core.redis_client import get_redis

logger = logging.getLogger(__name__)

_PUBLIC_API_PATHS: frozenset[str] = frozenset(
    {
        "/api/v1/auth/login",
        "/api/v1/auth/callback",
        "/api/v1/auth/refresh",
    }
)
_EXCLUDED_PREFIXES: frozenset[str] = frozenset(
    {"/docs", "/redoc", "/openapi", "/health", "/metrics"}
)
_SAFE_METHODS: frozenset[str] = frozenset({"GET", "HEAD", "OPTIONS"})


def _is_public(path: str) -> bool:
    if path in _PUBLIC_API_PATHS:
        return True
    return any(path.startswith(p) for p in _EXCLUDED_PREFIXES)


def _unauthorized(message: str) -> JSONResponse:
    return JSONResponse(
        status_code=401, content={"error": "Unauthorized", "message": message}
    )


def _forbidden(message: str) -> JSONResponse:
    return JSONResponse(
        status_code=403, content={"error": "Forbidden", "message": message}
    )


def _extract_token(request: Request) -> tuple[str | None, bool]:
    """Return (token, from_cookie).  from_cookie drives CSRF enforcement."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:], False
    cookie_token = request.cookies.get(SESSION_COOKIE)
    if cookie_token:
        return cookie_token, True
    return None, False


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if _is_public(request.url.path):
            return await call_next(request)

        token, from_cookie = _extract_token(request)
        if not token:
            return _unauthorized(
                "Missing credentials — provide Authorization: Bearer <token> "
                "or the session cookie."
            )

        # CSRF check for state-mutating cookie-based requests
        if from_cookie and request.method not in _SAFE_METHODS:
            csrf_cookie = request.cookies.get(CSRF_COOKIE)
            csrf_header = request.headers.get(CSRF_HEADER)
            if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
                return _forbidden("CSRF token missing or invalid.")

        try:
            payload = await validate_token(token)

            # Redis blacklist check using jti (short key, no full token stored)
            jti: str = payload.get("jti", "")
            keycloak_sub: str = payload.get("sub", "")

            redis_gen = get_redis()
            try:
                redis = await redis_gen.__anext__()
                blacklisted = await redis.get(f"oidc:blacklist:{jti}")
                # Also check per-user session invalidation (covers all tokens pre-logout)
                user_invalidated = await redis.get(f"oidc:invalidated:{keycloak_sub}")
                iat = int(payload.get("iat", 0))
                if user_invalidated and iat <= int(user_invalidated):
                    blacklisted = True
            finally:
                await redis_gen.aclose()

        except ValueError:
            return _unauthorized("Invalid or expired token.")
        except Exception:
            logger.exception("AuthMiddleware: unexpected error validating token")
            return JSONResponse(
                status_code=500,
                content={"error": "SystemFault", "message": "Internal authentication error."},
            )

        if blacklisted:
            return _unauthorized("Token has been revoked. Please log in again.")

        request.state.keycloak_sub = keycloak_sub
        request.state.token_payload = payload
        return await call_next(request)
