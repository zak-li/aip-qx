"""
cli/http/auth.py
----------------
Bearer-token injection middleware with transparent refresh.

`PxtlyAuth.auth_flow` implements httpx's generator-based auth protocol:

  1. Read the persisted TokenBundle.
  2. If absent → send the request with no Authorization header (skipped for
     endpoints that don't require auth, e.g. /health, /auth/login).
  3. If present and not expired → attach `Authorization: Bearer …`.
  4. If the response is 401 AND we have a refresh_token AND refresh_expires
     hasn't elapsed → run the refresh dance against Keycloak, persist the new
     bundle, retry the original request once with the new access token.

Refresh runs **inline** (sync httpx call inside the async generator). This
is intentional: the auth flow protocol is a generator, not an async one, so
we use a sync httpx.Client just for the refresh hop. The refresh URL itself
is not protected by Bearer, so this doesn't recurse.
"""
from __future__ import annotations

import logging
from collections.abc import Generator
from urllib.parse import urlparse

import httpx

from cli.security.tokens import (
    TokenBundle,
    delete_tokens,
    get_token_bundle,
    save_token_bundle,
)
from cli.settings import settings

log = logging.getLogger(__name__)

# Endpoints that must NEVER carry our Bearer token (we'd leak it).
_AUTH_FREE_PATHS = (
    "openid-connect/token",
    "openid-connect/auth",
    "/health",
)


def _is_auth_free(url: str) -> bool:
    return any(p in url for p in _AUTH_FREE_PATHS)


def _attempt_refresh(bundle: TokenBundle) -> TokenBundle | None:
    """
    POST to Keycloak's token endpoint with grant_type=refresh_token.
    Returns the new bundle on success, None on failure.
    """
    if not bundle.refresh_token or bundle.is_refresh_expired():
        return None

    token_url = (
        f"{settings.keycloak_url.rstrip('/')}"
        f"/realms/{settings.keycloak_realm}"
        f"/protocol/openid-connect/token"
    )
    data = {
        "grant_type": "refresh_token",
        "client_id": settings.keycloak_client_id,
        "refresh_token": bundle.refresh_token,
    }
    if settings.is_confidential_client and settings.keycloak_client_secret:
        data["client_secret"] = settings.keycloak_client_secret

    try:
        with httpx.Client(
            verify=settings.verify_param,
            timeout=httpx.Timeout(10.0),
        ) as client:
            resp = client.post(token_url, data=data)
        if resp.status_code != 200:
            log.warning("Refresh failed: HTTP %s", resp.status_code)
            return None
        new_bundle = TokenBundle.from_oidc_response(resp.json())
        save_token_bundle(new_bundle)
        log.info("Access token refreshed silently.")
        return new_bundle
    except httpx.RequestError as exc:
        log.warning("Refresh transport error: %s", exc)
        return None


class PxtlyAuth(httpx.Auth):
    """httpx Auth implementation with transparent token refresh on 401."""

    # We re-send the same request body after a 401+refresh, so the body
    # must be re-readable. httpx handles this automatically for dict/json
    # payloads — only raw streams need `requires_request_body = True`.
    requires_response_body = True

    def auth_flow(
        self, request: httpx.Request
    ) -> Generator[httpx.Request, httpx.Response, None]:
        url = str(request.url)

        if _is_auth_free(url):
            yield request
            return

        bundle = get_token_bundle()
        if bundle is None:
            yield request
            return

        request.headers["Authorization"] = f"{bundle.token_type} {bundle.access_token}"
        response = yield request

        if response.status_code != 401:
            return

        log.debug("401 on %s — attempting silent refresh.", urlparse(url).path)
        new_bundle = _attempt_refresh(bundle)
        if new_bundle is None:
            # Refresh failed: clear the bundle so subsequent calls don't
            # keep hitting 401 with a dead token. The caller will see the
            # original 401 and surface a clean "session expired" message.
            delete_tokens()
            return

        request.headers["Authorization"] = (
            f"{new_bundle.token_type} {new_bundle.access_token}"
        )
        yield request
