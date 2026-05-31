"""
cli/http/client.py
------------------
Shared async HTTP entrypoint for every api/ client.

Features:
  * Single httpx.AsyncClient per request (no pool leak across event loops).
  * PxtlyAuth middleware: Bearer injection + transparent refresh on 401.
  * Exponential backoff retry for 429 / 5xx / network errors.
  * Cache write-through and offline-mode fallback via cli/cache.py.
  * Typed error mapping — never raises raw httpx exceptions.

API stability: api_clients call `request("GET"/"POST"/…, url, **kwargs)`
and treat the return value as a `ResponseLike` (has `.json()`).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol, runtime_checkable

import httpx

from cli.http.auth import PxtlyAuth
from cli.http.exceptions import (
    AuthError,
    NetworkError,
    NotFoundError,
    PxtlyApiError,
    ServerError,
    ValidationError,
)
from cli.settings import settings

log = logging.getLogger(__name__)

_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF = 1.0
_RETRYABLE_CODES = {429, 500, 502, 503, 504}


@runtime_checkable
class ResponseLike(Protocol):
    status_code: int
    is_success: bool

    def json(self) -> Any: ...


def _raise_for_response(response: httpx.Response) -> None:
    if response.is_success:
        return
    try:
        body = response.json()
        detail = (
            body.get("detail")
            or body.get("error_description")
            or body.get("error")
            or response.text
        )
        if isinstance(detail, dict | list):
            detail = str(detail)
    except Exception:
        detail = response.text or f"HTTP {response.status_code}"

    code = response.status_code
    log.warning("API error %s: %s", code, str(detail)[:200])
    if code in (401, 403):
        raise AuthError(f"[{code}] {detail}", status_code=code)
    if code == 404:
        raise NotFoundError(f"[{code}] {detail}", status_code=code)
    if code in (400, 422):
        raise ValidationError(f"[{code}] {detail}", status_code=code)
    if code >= 500:
        raise ServerError(f"[{code}] {detail}", status_code=code)
    raise PxtlyApiError(f"[{code}] {detail}", status_code=code)


def _build_client(*, use_auth: bool) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        verify=settings.verify_param,
        timeout=httpx.Timeout(settings.http_timeout),
        auth=PxtlyAuth() if use_auth else None,
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        follow_redirects=False,  # don't silently follow redirects across hosts
    )


async def request(
    method: str,
    url: str,
    *,
    cache_key: str | None = None,
    cache_ttl: float = 3600.0,
    skip_auth: bool = False,
    **kwargs: Any,
) -> ResponseLike:
    """
    Execute an HTTP request with retry, refresh, and offline cache fallback.

    Parameters
    ----------
    cache_key : if given, the JSON body of a successful response is written
        to the local cache and used as a fallback if the network later fails.
    cache_ttl : seconds; how long a cached value is considered fresh.
    skip_auth : send no Authorization header (login/token-exchange endpoints).
    """
    from cli.cache import cache
    from cli.network_state import set_online

    last_exc: Exception | None = None

    for attempt in range(_RETRY_ATTEMPTS):
        try:
            async with _build_client(use_auth=not skip_auth) as client:
                response = await client.request(method, url, **kwargs)

            if (
                response.status_code in _RETRYABLE_CODES
                and attempt < _RETRY_ATTEMPTS - 1
            ):
                log.debug(
                    "Retryable %s on attempt %d/%d",
                    response.status_code, attempt + 1, _RETRY_ATTEMPTS,
                )
                await asyncio.sleep(_RETRY_BACKOFF * (2 ** attempt))
                continue

            _raise_for_response(response)

            set_online(True)
            if cache_key:
                try:
                    await cache.aset(cache_key, response.json(), ttl=cache_ttl)
                except Exception as exc:
                    log.debug("Cache write failed: %s", exc)
            return response

        except (AuthError, NotFoundError, ValidationError):
            # No retry — these are deterministic client errors.
            raise
        except ServerError as exc:
            last_exc = exc
            if attempt < _RETRY_ATTEMPTS - 1:
                await asyncio.sleep(_RETRY_BACKOFF * (2 ** attempt))
        except httpx.TimeoutException as exc:
            last_exc = NetworkError(f"Request timed out: {exc}")
            if attempt < _RETRY_ATTEMPTS - 1:
                await asyncio.sleep(_RETRY_BACKOFF * (2 ** attempt))
        except httpx.RequestError as exc:
            last_exc = NetworkError(f"Network error: {exc}")
            break  # transport failure is rarely transient enough to retry

    # All retries exhausted — try the offline cache.
    set_online(False)
    if cache_key:
        cached = await cache.aget(cache_key)
        if cached is not None:
            log.info("Serving stale cache for key=%s (offline)", cache_key)
            return CachedResponse(cached)

    raise last_exc or NetworkError("Request failed — no cache available.")


class CachedResponse:
    """Typed stand-in for httpx.Response used when serving from the cache."""

    def __init__(self, data: Any) -> None:
        self._data = data
        self.status_code = 200
        self.is_success = True

    def json(self) -> Any:
        return self._data
