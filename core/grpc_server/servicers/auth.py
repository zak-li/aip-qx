"""gRPC servicer for the Auth service — Keycloak OIDC edition.

Login / MFA RPCs are no longer implemented here; authentication is handled
entirely by Keycloak via the REST OIDC flow.  gRPC clients must obtain a
Keycloak access token through the REST API and supply it as:

    metadata = [("authorization", "Bearer <keycloak_access_token>")]

The AuthInterceptor validates every incoming RPC against the Keycloak JWKS.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import grpc
import grpc.aio
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.core.database import AsyncSessionLocal
from core.core.oidc import delete_keycloak_user
from core.core.redis_client import get_redis
from core.features.auth.models import User
from core.features.compliance.models import ComplianceRecord, KYCDocument
from core.features.transactions.models import Transaction
from core.features.zkp.models import ZKPCredential
from core.grpc_generated import auth_pb2, auth_pb2_grpc

logger = logging.getLogger(__name__)


class AuthServicer(auth_pb2_grpc.AuthServiceServicer):

    # ── Deprecated RPCs (authentication moved to Keycloak) ───────────────────

    async def Login(
        self,
        request: auth_pb2.LoginRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.TokenResponse:
        await context.abort(
            grpc.StatusCode.UNIMPLEMENTED,
            "Password-based login is no longer supported. "
            "Use the REST OIDC flow: GET /api/v1/auth/login",
        )

    async def SetupMFA(
        self,
        request: auth_pb2.SetupMFARequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.MFASetupResponse:
        await context.abort(
            grpc.StatusCode.UNIMPLEMENTED,
            "MFA is now managed by Keycloak. Configure it in the Keycloak account console.",
        )

    async def EnableMFA(
        self,
        request: auth_pb2.MFAVerifyRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.MFAActionResponse:
        await context.abort(
            grpc.StatusCode.UNIMPLEMENTED,
            "MFA is now managed by Keycloak.",
        )

    async def DisableMFA(
        self,
        request: auth_pb2.MFAVerifyRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.MFAActionResponse:
        await context.abort(
            grpc.StatusCode.UNIMPLEMENTED,
            "MFA is now managed by Keycloak.",
        )

    # ── Active RPCs ───────────────────────────────────────────────────────────

    async def Logout(
        self,
        request: auth_pb2.LogoutRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.LogoutResponse:
        payload: dict = context.user_payload  # type: ignore[attr-defined]
        jti: str = payload.get("jti", "")
        keycloak_sub: str = payload.get("sub", "")
        exp: int = int(payload.get("exp", 0))
        iat: int = int(payload.get("iat", 0))
        now_ts = int(datetime.now(UTC).timestamp())
        ttl = max(exp - now_ts, 1)

        async for redis in get_redis():
            if jti:
                await redis.setex(f"oidc:blacklist:{jti}", ttl, "1")
            if keycloak_sub:
                await redis.setex(f"oidc:invalidated:{keycloak_sub}", ttl, str(iat))

        # Best-effort Keycloak session revocation via the refresh token
        # (gRPC clients can optionally pass it as a request header; we skip here)
        return auth_pb2.LogoutResponse(message="Logged out successfully.")

    async def Refresh(
        self,
        request: auth_pb2.RefreshRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.TokenResponse:
        await context.abort(
            grpc.StatusCode.UNIMPLEMENTED,
            "Token refresh for gRPC: obtain a new token from Keycloak via "
            "POST /api/v1/auth/refresh or directly from the Keycloak token endpoint.",
        )

    async def GetMe(
        self,
        request: auth_pb2.GetMeRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.UserProfile:
        keycloak_sub: str = context.user_payload["sub"]  # type: ignore[attr-defined]
        async with AsyncSessionLocal() as db:
            user = await _get_user_by_sub(db, keycloak_sub)
        return _user_to_proto(user)

    async def ExportMyData(
        self,
        request: auth_pb2.ExportRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.UserDataExport:
        from sqlalchemy import or_

        keycloak_sub: str = context.user_payload["sub"]  # type: ignore[attr-defined]

        async with AsyncSessionLocal() as db:
            user = await _get_user_by_sub(db, keycloak_sub)
            user_id = user.id

            compliance = [
                {
                    "kyc_level": r.kyc_level,
                    "kyc_status": r.kyc_status,
                    "aml_score": float(r.aml_score),
                    "risk_category": r.risk_category,
                }
                for r in (
                    await db.execute(
                        select(ComplianceRecord).where(ComplianceRecord.participant_id == user_id)
                    )
                ).scalars().all()
            ]

            documents = [
                {"document_type": d.document_type, "issuing_country": d.issuing_country, "verified": d.verified}
                for d in (
                    await db.execute(select(KYCDocument).where(KYCDocument.user_id == user_id))
                ).scalars().all()
            ]

            transactions = [
                {"tx_ref": t.tx_ref, "tx_type": t.tx_type, "amount": float(t.amount) if t.amount else None}
                for t in (
                    await db.execute(
                        select(Transaction).where(
                            or_(
                                Transaction.initiator_id == user_id,
                                Transaction.from_owner_id == user_id,
                                Transaction.to_owner_id == user_id,
                            )
                        ).limit(500)
                    )
                ).scalars().all()
            ]

        payload = {
            "user": {
                "id": str(user.id),
                "email": user.email,
                "role": user.role,
                "org_id": str(user.org_id),
            },
            "compliance_records": compliance,
            "kyc_documents": documents,
            "transactions": transactions,
        }
        return auth_pb2.UserDataExport(json_payload=json.dumps(payload))

    async def DeleteMyAccount(
        self,
        request: auth_pb2.DeleteRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.DeleteResponse:
        keycloak_sub: str = context.user_payload["sub"]  # type: ignore[attr-defined]
        now = datetime.now(UTC)

        async with AsyncSessionLocal() as db:
            user = await _get_user_by_sub(db, keycloak_sub)
            user_id = user.id

            user.email = f"deleted-{user_id}@anonymised.invalid"
            user.first_name = None
            user.last_name = None
            user.phone = None
            user.keycloak_sub = None
            user.is_active = False

            await db.execute(delete(KYCDocument).where(KYCDocument.user_id == user_id))
            await db.execute(
                update(ZKPCredential)
                .where(ZKPCredential.user_id == user_id, ~ZKPCredential.revoked)
                .values(revoked=True, revoked_at=now, revoked_reason="gdpr_erasure")
            )
            await db.commit()

        async for redis in get_redis():
            await redis.setex(
                f"oidc:invalidated:{keycloak_sub}", 86400 * 30, str(int(now.timestamp()))
            )

        if keycloak_sub:
            try:
                await delete_keycloak_user(keycloak_sub)
            except Exception:
                logger.warning("Could not delete Keycloak user %s", keycloak_sub)

        return auth_pb2.DeleteResponse(message="Account anonymised (GDPR Art. 17).")


# ─────────────────────────── helpers ─────────────────────────────────────────

async def _get_user_by_sub(db: AsyncSession, keycloak_sub: str) -> User:
    user = (
        await db.execute(select(User).where(User.keycloak_sub == keycloak_sub))
    ).scalar_one_or_none()
    if not user:
        raise ValueError(f"No user found for keycloak_sub={keycloak_sub}")
    return user


def _user_to_proto(user: User) -> auth_pb2.UserProfile:
    return auth_pb2.UserProfile(
        id=str(user.id),
        email=user.email or "",
        first_name=user.first_name or "",
        last_name=user.last_name or "",
        role=user.role or "",
        org_id=str(user.org_id) if user.org_id else "",
        mfa_enabled=False,   # MFA managed by Keycloak
        created_at=user.created_at.isoformat() if user.created_at else "",
        last_login=user.last_login.isoformat() if user.last_login else "",
    )
