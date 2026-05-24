"""Cached loader for compliance fixtures (sanctions lists + AML indicators).

The fixtures file is currently the runtime source of truth — re-reading it
from disk on every transaction is wasteful and races with edits. This loader
caches the parsed JSON in memory and invalidates the cache when the file
mtime changes.

In production a detached ed25519 signature must accompany the manifest:

    database/fixtures/json/compliance_kyc_aml.json
    database/fixtures/json/compliance_kyc_aml.json.sig    ← signature (raw 64 bytes)

The verification key lives in the env var ``SANCTIONS_MANIFEST_PUBKEY_HEX``
(64 hex chars). When the env var and signature are present, the manifest is
rejected on signature mismatch. When either is missing the loader logs a
loud warning so production deployments can wire alerting on it.

NOTE: this is still a stop-gap. The endgame is to fetch signed feeds
directly from OFAC/UN/EU/UK HMT with their own rotation policies.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_FIXTURES_PATH = Path("database/fixtures/json/compliance_kyc_aml.json").resolve()
_SIGNATURE_PATH = _FIXTURES_PATH.with_suffix(_FIXTURES_PATH.suffix + ".sig")

_lock = threading.Lock()
_cached_data: dict[str, Any] = {}
_cached_mtime: float | None = None


def _verify_signature(raw: bytes) -> bool:
    """Return True iff the manifest signature matches the configured key.

    Returns True when no signature workflow is configured (dev mode), but
    emits a warning so the absence is visible. Returns False only when both
    the key and signature are present but mismatch — that case must be
    treated as tampering.
    """
    pubkey_hex = os.getenv("SANCTIONS_MANIFEST_PUBKEY_HEX", "").strip()

    if not pubkey_hex:
        logger.warning(
            "SANCTIONS_MANIFEST_PUBKEY_HEX not configured — manifest signature not verified."
        )
        return True

    if not _SIGNATURE_PATH.is_file():
        logger.warning(
            "Sanctions manifest signature missing at %s — refusing to trust manifest",
            _SIGNATURE_PATH,
        )
        return False

    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        pub_bytes = bytes.fromhex(pubkey_hex)
        sig_bytes = _SIGNATURE_PATH.read_bytes()
        Ed25519PublicKey.from_public_bytes(pub_bytes).verify(sig_bytes, raw)
        return True
    except InvalidSignature:
        logger.error("Sanctions manifest signature verification FAILED — manifest rejected.")
        return False
    except Exception:
        logger.exception("Sanctions manifest signature verification raised — manifest rejected.")
        return False


def _read_fixtures() -> dict[str, Any]:
    global _cached_data, _cached_mtime
    try:
        mtime = _FIXTURES_PATH.stat().st_mtime
    except FileNotFoundError:
        if _cached_data:
            return _cached_data
        logger.warning("Compliance fixture file missing: %s", _FIXTURES_PATH)
        return {}

    if _cached_mtime == mtime and _cached_data:
        return _cached_data

    try:
        raw = _FIXTURES_PATH.read_bytes()
    except OSError:
        logger.exception("Failed to read compliance fixture file")
        return _cached_data or {}

    if not _verify_signature(raw):
        # Keep serving the previously trusted snapshot; never fall back to
        # an unverified manifest in production.
        return _cached_data or {}

    try:
        data = json.loads(raw.decode("utf-8-sig"))
        if not isinstance(data, dict):
            data = {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.exception("Failed to parse compliance fixture JSON")
        return _cached_data or {}

    _cached_data = data
    _cached_mtime = mtime
    return data


def load_fixtures() -> dict[str, Any]:
    """Return the parsed fixture document, cached and refreshed on mtime change."""
    with _lock:
        return _read_fixtures()


def get_sanctions_lists() -> dict[str, list[str]]:
    raw = load_fixtures().get("sanctions_lists", {})
    if not isinstance(raw, dict):
        return {}
    return raw


def get_participants() -> list[dict[str, Any]]:
    raw = load_fixtures().get("participants", [])
    if not isinstance(raw, list):
        return []
    return raw


def invalidate_cache() -> None:
    """Force the next call to re-read from disk. Useful in tests."""
    global _cached_data, _cached_mtime
    with _lock:
        _cached_data = {}
        _cached_mtime = None
