"""Credential issuance: the platform signs an eligibility claim over the user's
public key, making the credential verifiable without knowing the user's identity.

Claim structure:
  {
    "Y_x": "<hex>",
    "Y_y": "<hex>",
    "age_ok": bool,
    "kyc_ok": bool,
    "not_sanctioned": bool,
    "kyc_level": int,
    "issued_at": "<iso>",
    "expires_at": "<iso>"
  }

The signature is ECDSA over SHA-256(canonical_json(claim)), using the
platform's secp256k1 private key stored in Vault (or env for dev).
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.features.compliance.models import ComplianceRecord
from backend.features.zkp.models import ZKPCredential
from backend.features.zkp.platform_key import (
    get_signing_key,
    public_key_xy_hex,
)

logger = logging.getLogger(__name__)

# Validity window for credentials
_CREDENTIAL_TTL_DAYS = 90


def _canonical_json(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _sign_claim(claim: dict) -> str:
    """ECDSA-sign the claim using the platform private key (DER-encoded hex)."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric.ec import ECDSA

    payload = _canonical_json(claim)
    sig = get_signing_key().sign(payload, ECDSA(hashes.SHA256()))
    return sig.hex()


def _platform_public_key_hex() -> tuple[str, str]:
    """Return (x_hex, y_hex) of the platform ECDSA public key."""
    return public_key_xy_hex()


async def _check_eligibility(
    user_id: uuid.UUID, db: AsyncSession
) -> tuple[bool, bool, bool, int]:
    """Return (age_ok, kyc_ok, not_sanctioned, kyc_level) for a user."""
    stmt = (
        select(ComplianceRecord)
        .where(ComplianceRecord.participant_id == user_id)
        .order_by(ComplianceRecord.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()

    if record is None:
        # No compliance record → deny by default. Issuing a credential that
        # claims `not_sanctioned=True` for an unscreened user would silently
        # bypass sanctions enforcement.
        return False, False, False, 0

    kyc_ok = record.kyc_status in ("APPROUVE", "VALIDE") and not record.is_expired
    not_sanctioned = not record.sanctions_hit
    kyc_level = record.kyc_level

    # Age: we don't store DOB; KYC level ≥ 2 implies identity was verified including age
    age_ok = kyc_level >= 2

    return age_ok, kyc_ok, not_sanctioned, kyc_level


async def issue_credential(
    user_id: uuid.UUID,
    public_key_x: str,
    public_key_y: str,
    db: AsyncSession,
) -> ZKPCredential:
    """Issue or refresh a ZKP credential for a user.

    If a non-revoked credential for this (user, pubkey) pair exists,
    return it. Otherwise create a new one.
    """
    # Check for existing active credential
    stmt = select(ZKPCredential).where(
        ZKPCredential.user_id == user_id,
        ZKPCredential.public_key_x == public_key_x,
        ~ZKPCredential.revoked,
    ).order_by(ZKPCredential.issued_at.desc()).limit(1)
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing and existing.expires_at > datetime.now(UTC):
        return existing

    age_ok, kyc_ok, not_sanctioned, kyc_level = await _check_eligibility(user_id, db)

    now = datetime.now(UTC)
    expires = now + timedelta(days=_CREDENTIAL_TTL_DAYS)

    claim = {
        "Y_x": public_key_x,
        "Y_y": public_key_y,
        "age_ok": age_ok,
        "kyc_ok": kyc_ok,
        "not_sanctioned": not_sanctioned,
        "kyc_level": kyc_level,
        "issued_at": now.isoformat(),
        "expires_at": expires.isoformat(),
    }
    sig = _sign_claim(claim)

    credential = ZKPCredential(
        id=uuid.uuid4(),
        user_id=user_id,
        public_key_x=public_key_x,
        public_key_y=public_key_y,
        age_ok=age_ok,
        kyc_ok=kyc_ok,
        not_sanctioned=not_sanctioned,
        kyc_level=kyc_level,
        issuer_sig=sig,
        issued_at=now,
        expires_at=expires,
        revoked=False,
    )
    db.add(credential)
    await db.commit()
    await db.refresh(credential)
    return credential


def build_claim_dict(credential: ZKPCredential) -> dict:
    return {
        "Y_x": credential.public_key_x,
        "Y_y": credential.public_key_y,
        "age_ok": credential.age_ok,
        "kyc_ok": credential.kyc_ok,
        "not_sanctioned": credential.not_sanctioned,
        "kyc_level": credential.kyc_level,
        "issued_at": credential.issued_at.isoformat(),
        "expires_at": credential.expires_at.isoformat(),
    }
