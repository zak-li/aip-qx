"""gRPC servicer for the ZKP (zk-KYC) service."""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

import grpc
import grpc.aio
from sqlalchemy import select

from core.core.database import AsyncSessionLocal
from core.features.zkp.issuer import build_claim_dict, issue_credential
from core.features.zkp.merkle import get_sanctions_tree
from core.features.zkp.models import ZKPCredential
from core.features.zkp.verifier import verify_proof
from core.grpc_generated import zkp_pb2, zkp_pb2_grpc

logger = logging.getLogger(__name__)


class ZKPServicer(zkp_pb2_grpc.ZKPServiceServicer):

    async def SetupKey(
        self,
        request: zkp_pb2.SetupKeyRequest,
        context: grpc.aio.ServicerContext,
    ) -> zkp_pb2.SetupKeyResponse:
        user_id = uuid.UUID(context.user_payload["sub"])
        async with AsyncSessionLocal() as db:
            try:
                credential = await issue_credential(
                    user_id=user_id,
                    public_key_x=request.public_key_x,
                    public_key_y=request.public_key_y,
                    db=db,
                )
            except Exception as exc:
                logger.error(f"[ZKP] Credential issuance failed for {user_id}: {exc}")
                await context.abort(grpc.StatusCode.INTERNAL, f"Credential issuance failed: {exc}")

        tree = get_sanctions_tree()
        claim = build_claim_dict(credential)

        return zkp_pb2.SetupKeyResponse(
            credential_id=str(credential.id),
            claim=str(claim),
            issuer_sig=credential.issuer_sig or "",
            expires_at=credential.expires_at.isoformat() if credential.expires_at else "",
            sanctions_tree_root=tree.root.hex(),
        )

    async def VerifyProof(
        self,
        request: zkp_pb2.ProofRequest,
        context: grpc.aio.ServicerContext,
    ) -> zkp_pb2.ProofResponse:
        async with AsyncSessionLocal() as db:
            valid, message = await verify_proof(
                public_key_x=request.public_key_x,
                public_key_y=request.public_key_y,
                proof_Rx=request.proof_rx,
                proof_Ry=request.proof_ry,
                proof_s=request.proof_s,
                purpose=request.purpose,
                context=request.context,
                nullifier_hex=request.nullifier,
                credential_claim=request.credential_claim,
                credential_sig=request.credential_sig,
                db=db,
            )

        if not valid:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, message)

        return zkp_pb2.ProofResponse(valid=True, purpose=request.purpose, message=message)

    async def GetZKPStatus(
        self,
        request: zkp_pb2.StatusRequest,
        context: grpc.aio.ServicerContext,
    ) -> zkp_pb2.ZKPStatusResponse:
        user_id = uuid.UUID(context.user_payload["sub"])
        async with AsyncSessionLocal() as db:
            stmt = (
                select(ZKPCredential)
                .where(ZKPCredential.user_id == user_id)
                .order_by(ZKPCredential.issued_at.desc())
                .limit(1)
            )
            credential = (await db.execute(stmt)).scalar_one_or_none()

        tree = get_sanctions_tree()

        if credential is None:
            return zkp_pb2.ZKPStatusResponse(
                has_credential=False,
                age_ok=False,
                kyc_ok=False,
                not_sanctioned=False,
                kyc_level=0,
                revoked=False,
                sanctions_tree_root=tree.root.hex(),
            )

        return zkp_pb2.ZKPStatusResponse(
            credential_id=str(credential.id),
            has_credential=True,
            age_ok=credential.age_ok,
            kyc_ok=credential.kyc_ok,
            not_sanctioned=credential.not_sanctioned,
            kyc_level=credential.kyc_level,
            expires_at=credential.expires_at.isoformat() if credential.expires_at else "",
            revoked=credential.revoked,
            sanctions_tree_root=tree.root.hex(),
        )

    async def RevokeCredential(
        self,
        request: zkp_pb2.RevokeRequest,
        context: grpc.aio.ServicerContext,
    ) -> zkp_pb2.RevokeResponse:
        caller_id = uuid.UUID(context.user_payload["sub"])
        caller_role = context.user_payload.get("role", "")

        async with AsyncSessionLocal() as db:
            stmt = select(ZKPCredential).where(
                ZKPCredential.id == uuid.UUID(request.credential_id)
            )
            credential = (await db.execute(stmt)).scalar_one_or_none()

            if credential is None:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Credential not found")

            if credential.user_id != caller_id and caller_role not in ("SUPER_ADMIN", "COMPLIANCE_OFFICER"):
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Not authorised to revoke this credential")

            credential.revoked = True
            credential.revoked_at = datetime.now(UTC)
            credential.revoked_reason = request.reason or "manual_revocation"
            await db.commit()

        return zkp_pb2.RevokeResponse(
            status="revoked",
            credential_id=request.credential_id,
        )
