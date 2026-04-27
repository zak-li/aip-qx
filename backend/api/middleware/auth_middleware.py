import logging
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from backend.core.auth_cookies import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE
from backend.core.redis_client import get_redis
from backend.core.security import decode_token

logger = logging.getLogger(__name__)

# Strict allow-list of paths that bypass JWT validation.
_EXCLUDED_EXACT = frozenset({
    "/",
    "/api/v1/auth/login",
    "/health",
    "/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon.svg",
    "/robots.txt",
    "/site.webmanifest",
})

_EXCLUDED_PREFIX = (
    "/assets/",
    "/animations/",
    "/docs/",
)

# CSRF check applies to mutating verbs only. GET/HEAD/OPTIONS are exempt
# because the cookie-only path does not let cross-origin JS read the
# response body anyway.
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _is_excluded(path: str) -> bool:
    if path in _EXCLUDED_EXACT:
        return True
    return any(path.startswith(prefix) for prefix in _EXCLUDED_PREFIX)


def _unauthorized(message: str) -> JSONResponse:
    return JSONResponse(status_code=401, content={"error": "Unauthorized", "message": message})


def _forbidden(message: str) -> JSONResponse:
    return JSONResponse(status_code=403, content={"error": "Forbidden", "message": message})


def _extract_credentials(request: Request) -> tuple[str | None, bool]:
    """Return ``(jwt, came_from_cookie)`` or ``(None, False)`` if absent.

    Header takes precedence over cookie so callers using both end up on the
    legacy path with no CSRF requirement.
    """
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1], False

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
        path = request.url.path
        if _is_excluded(path):
            return await call_next(request)

        token, from_cookie = _extract_credentials(request)
        if not token:
            return _unauthorized(
                "Missing credentials. Use Authorization: Bearer <token> or the session cookie.",
            )

        # CSRF double-submit: when the JWT comes from the cookie, mutating
        # requests must echo the CSRF cookie via the X-CSRF-Token header.
        if from_cookie and request.method not in _SAFE_METHODS:
            csrf_cookie = request.cookies.get(CSRF_COOKIE)
            csrf_header = request.headers.get(CSRF_HEADER)
            if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
                return _forbidden("CSRF token missing or invalid.")

        try:
            redis_gen = get_redis()
            redis_conn = await redis_gen.__anext__()
            try:
                is_blacklisted = await redis_conn.get(f"blacklist:{token}")

                payload = decode_token(token)
                user_id = payload.get("sub")
                iat = int(payload.get("iat", 0))

                last_logout_raw = await redis_conn.get(f"token:invalidated:{user_id}")
                if last_logout_raw and iat <= int(last_logout_raw):
                    is_blacklisted = True
            finally:
                await redis_gen.aclose()
        except ValueError:
            return _unauthorized("Invalid or expired token.")
        except Exception:
            logger.exception("Auth middleware: unexpected error validating token")
            return JSONResponse(
                status_code=500,
                content={"error": "SystemFault", "message": "Internal authentication error."},
            )

        if is_blacklisted:
            return _unauthorized("Token has been revoked. Please log in again.")

        request.state.user_id = str(user_id)
        return await call_next(request)
