"""
cli/http/exceptions.py
----------------------
Typed exception hierarchy raised by the HTTP layer. All API clients,
commands, and UI code import these — never `httpx.HTTPError` directly.
"""
from __future__ import annotations


class PxtlyApiError(Exception):
    """Base class for any error originating from the API or transport."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class AuthError(PxtlyApiError):
    """401 / 403 — token missing, expired, or insufficient privileges."""


class NotFoundError(PxtlyApiError):
    """404 — resource does not exist."""


class ValidationError(PxtlyApiError):
    """400 / 422 — request body or query params rejected by the API."""


class ServerError(PxtlyApiError):
    """5xx — backend failure (DB, Fabric peer, Keycloak, …)."""


class NetworkError(PxtlyApiError):
    """
    Connection refused, DNS failure, TLS handshake error, or timeout.
    Distinct from ServerError because retry/backoff strategy differs.
    """
