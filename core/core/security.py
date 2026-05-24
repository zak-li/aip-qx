"""Security utilities — Keycloak OIDC edition.

All production authentication is delegated to Keycloak.
This module re-exports the validate_token/extract_role functions and also
provides lightweight test-only helpers so existing unit-test fixtures compile
without a real Keycloak instance.
"""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from jose import jwt as _jose_jwt

from core.core.oidc import extract_role, validate_token

__all__ = ["validate_token", "extract_role", "create_access_token", "hash_password"]

# Fixed signing key used exclusively by test fixtures.
# Tests that need to call validate_token must patch it to decode with this key.
_TEST_SIGNING_KEY = "ci-test-jwt-signing-key-at-least-32-chars-long!"


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Create a HS256-signed JWT for use in unit-test fixtures only.

    Production code validates RS256 tokens issued by Keycloak; this helper
    exists so conftest.py fixtures can generate tokens without a live Keycloak.
    """
    payload = dict(data)
    expire = datetime.now(UTC) + (expires_delta or timedelta(minutes=15))
    payload.update({"exp": expire, "iat": datetime.now(UTC), "jti": str(uuid4())})
    return _jose_jwt.encode(payload, _TEST_SIGNING_KEY, algorithm="HS256")


def hash_password(password: str) -> str:
    """Stub retained for backward-compat with test fixtures.

    The production User model no longer stores hashed passwords (Keycloak owns
    credentials). Tests that create User rows should omit the password entirely.
    """
    _ = password
    return "$test$stub"
