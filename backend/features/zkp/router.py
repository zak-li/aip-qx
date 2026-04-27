"""ZKP (Zero-Knowledge Proof) API endpoints for decentralised zk-KYC."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, UTC

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies import get_db, get_current_user
from backend.features.auth.models import User
from backend.features.zkp.issuer import issue_credential, build_claim_dict
from backend.features.zkp.merkle import get_sanctions_tree
from backend.features.zkp.models import ZKPCredential
from backend.features.zkp.schemas import (
    SetupKeyRequest, SetupKeyResponse,
    ProofRequest, ProofResponse,
    ZKPStatusResponse,
)
from backend.features.zkp.verifier import verify_proof

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/setup-key", response_model=SetupKeyResponse, status_code=201)
async def setup_key(
    req: SetupKeyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register user's public key and receive a signed eligibility credential.

    The server evaluates KYC/AML status and issues a credential claim signed
    with the platform ECDSA key. The private key never leaves the client.
    """
    try:
        credential = await issue_credential(
            user_id=current_user.id,
            public_key_x=req.public_key_x,
            public_key_y=req.public_key_y,
            db=db,
        )
    except Exception as exc:
        logger.error(f"[ZKP] Credential issuance failed for {current_user.id}: {exc}")
        raise HTTPException(status_code=500, detail=f"Credential issuance failed: {exc}")

    tree = get_sanctions_tree()
    claim = build_claim_dict(credential)

    return SetupKeyResponse(
        credential_id=str(credential.id),
        claim=claim,
        issuer_sig=credential.issuer_sig,
        expires_at=credential.expires_at,
        sanctions_tree_root=tree.root.hex(),
    )


@router.post("/verify", response_model=ProofResponse)
async def verify(
    req: ProofRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit a Schnorr ZKP proof for a specific purpose.

    The server verifies:
    - Platform-issued credential signature
    - Credential freshness and non-revocation
    - Purpose-specific claim requirements
    - Mathematical validity of the Schnorr proof
    - Nullifier not previously used (replay prevention)

    On success the nullifier is consumed and the proof is accepted.
    """
    valid, message = await verify_proof(
        public_key_x=req.public_key_x,
        public_key_y=req.public_key_y,
        proof_Rx=req.proof_Rx,
        proof_Ry=req.proof_Ry,
        proof_s=req.proof_s,
        purpose=req.purpose,
        context=req.context,
        nullifier_hex=req.nullifier,
        credential_claim=req.credential_claim,
        credential_sig=req.credential_sig,
        db=db,
    )

    if not valid:
        logger.warning(f"[ZKP] Proof rejected for purpose={req.purpose}: {message}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )

    logger.info(f"[ZKP] Proof accepted for purpose={req.purpose}")
    return ProofResponse(valid=True, purpose=req.purpose, message=message)


@router.get("/status", response_model=ZKPStatusResponse)
async def zkp_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the ZKP credential status for the current user."""
    stmt = (
        select(ZKPCredential)
        .where(ZKPCredential.user_id == current_user.id)
        .order_by(ZKPCredential.issued_at.desc())
        .limit(1)
    )
    credential = (await db.execute(stmt)).scalar_one_or_none()
    tree = get_sanctions_tree()

    if credential is None:
        return ZKPStatusResponse(
            credential_id=None,
            has_credential=False,
            age_ok=False,
            kyc_ok=False,
            not_sanctioned=False,
            kyc_level=0,
            expires_at=None,
            revoked=False,
            sanctions_tree_root=tree.root.hex(),
        )

    return ZKPStatusResponse(
        credential_id=str(credential.id),
        has_credential=True,
        age_ok=credential.age_ok,
        kyc_ok=credential.kyc_ok,
        not_sanctioned=credential.not_sanctioned,
        kyc_level=credential.kyc_level,
        expires_at=credential.expires_at,
        revoked=credential.revoked,
        sanctions_tree_root=tree.root.hex(),
    )


@router.post("/revoke/{credential_id}", status_code=200)
async def revoke_credential(
    credential_id: str,
    reason: str = "manual_revocation",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a credential (admin or credential owner only)."""
    stmt = select(ZKPCredential).where(ZKPCredential.id == uuid.UUID(credential_id))
    credential = (await db.execute(stmt)).scalar_one_or_none()
    if credential is None:
        raise HTTPException(status_code=404, detail="Credential not found")

    if credential.user_id != current_user.id and current_user.role not in (
        "SUPER_ADMIN", "COMPLIANCE_OFFICER"
    ):
        raise HTTPException(status_code=403, detail="Not authorised to revoke this credential")

    credential.revoked = True
    credential.revoked_at = datetime.now(UTC)
    credential.revoked_reason = reason
    await db.commit()

    return {"status": "revoked", "credential_id": credential_id}
