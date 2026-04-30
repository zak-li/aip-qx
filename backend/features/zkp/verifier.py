"""ZKP proof verifier.

Checks (in order):
  1. Credential signature is valid (issued by this platform)
  2. Credential has not expired and is not revoked
  3. Credential satisfies the required claims for the requested purpose
  4. Schnorr proof is mathematically valid
  5. Nullifier has not been used before (replay prevention)

If all checks pass, the nullifier is persisted and the proof is accepted.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.features.zkp.crypto import SchnorrProof, is_on_curve, point_from_hex, schnorr_verify
from backend.features.zkp.models import ZKPCredential, ZKPNullifier
from backend.features.zkp.platform_key import get_verification_key

logger = logging.getLogger(__name__)

# Purpose → required claims map.
# Each purpose declares the minimum claim attributes a credential must hold
# for the proof to be accepted. A purpose may require age_ok (≥ 18), kyc_ok,
# not_sanctioned, and/or a minimum kyc_level.
_PURPOSE_CLAIMS: dict[str, dict] = {
    "asset_transfer":   {"age_ok": True, "kyc_ok": True, "not_sanctioned": True, "kyc_level": 2},
    "asset_create":     {"age_ok": True, "kyc_ok": True, "not_sanctioned": True, "kyc_level": 3},
    "kyc_gate":         {"kyc_ok": True},
    "compliance_check": {"not_sanctioned": True},
}


def _canonical_json(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _verify_issuer_sig(claim: dict, sig_hex: str) -> bool:
    """Verify the platform ECDSA signature on a credential claim.

    Only the platform PUBLIC key is used here — the verifier never has access
    to the private key.
    """
    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric.ec import ECDSA

        payload = _canonical_json(claim)
        get_verification_key().verify(bytes.fromhex(sig_hex), payload, ECDSA(hashes.SHA256()))
        return True
    except Exception as exc:
        logger.warning(f"[ZKP] Issuer sig verification failed: {exc}")
        return False


def _check_purpose_claims(credential: ZKPCredential, purpose: str) -> tuple[bool, str]:
    required = _PURPOSE_CLAIMS.get(purpose)
    if required is None:
        return False, f"Unknown purpose: {purpose}"

    if required.get("age_ok") and not credential.age_ok:
        return False, "Proof does not satisfy age requirement (≥ 18)"
    if required.get("kyc_ok") and not credential.kyc_ok:
        return False, "Proof does not satisfy KYC requirement"
    if required.get("not_sanctioned") and not credential.not_sanctioned:
        return False, "Proof does not satisfy sanctions clearance requirement"
    min_level = required.get("kyc_level", 0)
    if credential.kyc_level < min_level:
        return False, f"KYC level {credential.kyc_level} below required {min_level}"

    return True, "ok"


async def verify_proof(
    public_key_x: str,
    public_key_y: str,
    proof_Rx: str,
    proof_Ry: str,
    proof_s: str,
    purpose: str,
    context: str,
    nullifier_hex: str,
    credential_claim: dict,
    credential_sig: str,
    db: AsyncSession,
) -> tuple[bool, str]:
    """Full ZKP verification pipeline. Returns (valid, reason)."""

    # 1. Verify issuer signature on credential claim
    if not _verify_issuer_sig(credential_claim, credential_sig):
        return False, "Invalid credential signature — not issued by this platform"

    # 2. Credential expiry check
    expires_at_str = credential_claim.get("expires_at", "")
    try:
        expires_at = datetime.fromisoformat(expires_at_str)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at < datetime.now(UTC):
            return False, "Credential has expired"
    except ValueError:
        return False, "Credential has invalid expiry date"

    # 3. Public key in claim must match proof public key
    if credential_claim.get("Y_x") != public_key_x or credential_claim.get("Y_y") != public_key_y:
        return False, "Public key mismatch between credential and proof"

    # 4. Check revocation in DB
    stmt = select(ZKPCredential).where(
        ZKPCredential.public_key_x == public_key_x,
        ZKPCredential.revoked.is_(True),
    ).limit(1)
    revoked = (await db.execute(stmt)).scalar_one_or_none()
    if revoked:
        return False, "Credential has been revoked"

    # 5. Purpose-specific claim requirements
    class _FakeCred:
        age_ok = credential_claim.get("age_ok", False)
        kyc_ok = credential_claim.get("kyc_ok", False)
        not_sanctioned = credential_claim.get("not_sanctioned", False)
        kyc_level = credential_claim.get("kyc_level", 0)

    ok, reason = _check_purpose_claims(_FakeCred(), purpose)  # type: ignore[arg-type]
    if not ok:
        return False, reason

    # 6. Schnorr proof verification (mathematical)
    try:
        Y = point_from_hex(public_key_x, public_key_y)
        proof = SchnorrProof(
            Rx=int(proof_Rx, 16),
            Ry=int(proof_Ry, 16),
            s=int(proof_s, 16),
        )
    except (ValueError, TypeError):
        return False, "Malformed proof coordinates"

    if not is_on_curve(Y):
        return False, "Public key is not on secp256k1"

    context_bytes = f"{purpose}:{context}".encode()
    if not schnorr_verify(proof, Y, context_bytes):
        return False, "Schnorr proof is mathematically invalid"

    # 7. Nullifier replay check
    stmt2 = select(ZKPNullifier).where(ZKPNullifier.nullifier_hex == nullifier_hex).limit(1)
    existing = (await db.execute(stmt2)).scalar_one_or_none()
    if existing:
        return False, "Nullifier already used — proof replayed"

    # 8. Persist nullifier
    nullifier = ZKPNullifier(
        id=uuid.uuid4(),
        nullifier_hex=nullifier_hex,
        purpose=purpose,
        public_key_x=public_key_x,
    )
    db.add(nullifier)
    await db.commit()

    return True, "Proof accepted"
