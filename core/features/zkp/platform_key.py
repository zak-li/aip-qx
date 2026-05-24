"""Platform ECDSA signing key management for ZKP credentials.

Centralises the loading of the platform secret so issuer and verifier share a
single source of truth. In production the secret MUST come from the environment
or Vault — the dev default is rejected to prevent forgeable credentials.

The verifier uses ONLY the public key — never the private key. Splitting the
two helpers makes that boundary explicit.
"""
from __future__ import annotations

import functools
import hashlib
import os

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric.ec import (
    SECP256K1,
    EllipticCurvePrivateKey,
    EllipticCurvePublicKey,
    derive_private_key,
)

from core.config import settings

# secp256k1 curve order
_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141

_DEV_DEFAULT_SECRET = "dev-platform-zkp-secret-change-in-prod"  # noqa: S105


def _load_secret() -> str:
    secret = os.getenv("PLATFORM_ZKP_SECRET", _DEV_DEFAULT_SECRET)
    if settings.environment == "production" and secret == _DEV_DEFAULT_SECRET:
        raise RuntimeError(
            "PLATFORM_ZKP_SECRET is unset or using the dev default in production. "
            "Refusing to operate — credentials would be forgeable."
        )
    return secret


@functools.lru_cache(maxsize=1)
def _private_key() -> EllipticCurvePrivateKey:
    secret = _load_secret()
    raw = hashlib.sha256(secret.encode()).digest()
    scalar = int.from_bytes(raw, "big")
    scalar = (scalar % (_N - 1)) + 1
    return derive_private_key(scalar, SECP256K1(), default_backend())


def get_signing_key() -> EllipticCurvePrivateKey:
    """Return the platform private key. Issuer-only — never call from verifier."""
    return _private_key()


@functools.lru_cache(maxsize=1)
def get_verification_key() -> EllipticCurvePublicKey:
    """Return the platform public key for credential signature verification."""
    return _private_key().public_key()


def public_key_xy_hex() -> tuple[str, str]:
    pub = get_verification_key().public_numbers()
    return hex(pub.x), hex(pub.y)
