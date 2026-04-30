"""gRPC servicer for the Auth service."""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

import grpc
import grpc.aio
import pyotp
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.core.database import AsyncSessionLocal
from backend.core.redis_client import get_redis
from backend.core.security import create_access_token, decode_token, verify_password
from backend.features.auth.models import User
from backend.features.compliance.models import ComplianceRecord, KYCDocument
from backend.features.transactions.models import Transaction
from backend.features.zkp.models import ZKPCredential
from backend.grpc_generated import auth_pb2, auth_pb2_grpc

logger = logging.getLogger(__name__)

_MAX_FAILED = 5
_LOCKOUT_MINUTES = 15


class AuthServicer(auth_pb2_grpc.AuthServiceServicer):

    async def Login(
        self,
        request: auth_pb2.LoginRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.TokenResponse:
        async with AsyncSessionLocal() as db:
            stmt = select(User).where(User.email == request.email)
            user = (await db.execute(stmt)).scalar_one_or_none()

            if not user or not verify_password(request.password, user.hashed_password):
                if user:
                    user.failed_login_count = (user.failed_login_count or 0) + 1
                    if user.failed_login_count >= _MAX_FAILED:
                        user.locked_until = datetime.now(UTC) + timedelta(minutes=_LOCKOUT_MINUTES)
                    await db.commit()
                await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid credentials")

            if user.is_locked:
                await context.abort(
                    grpc.StatusCode.PERMISSION_DENIED,
                    f"Account locked until {user.locked_until}",
                )

            if user.mfa_enabled and user.mfa_secret:
                if not request.mfa_code:
                    return auth_pb2.TokenResponse(
                        access_token="", token_type="bearer", expires_in=0, mfa_required=True  # noqa: S106
                    )
                totp = pyotp.TOTP(user.mfa_secret)
                if not totp.verify(request.mfa_code, valid_window=1):
                    await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid MFA code")

            user.failed_login_count = 0
            user.locked_until = None
            user.last_login = datetime.now(UTC)
            await db.commit()

            token_data = {"sub": str(user.id), "role": user.role, "org_id": str(user.org_id)}
            access_token = create_access_token(
                data=token_data,
                expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
            )
            expires_in = settings.access_token_expire_minutes * 60

        return auth_pb2.TokenResponse(
            access_token=access_token,
            token_type="bearer",  # noqa: S106
            expires_in=expires_in,
            mfa_required=False,
        )

    async def Logout(
        self,
        request: auth_pb2.LogoutRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.LogoutResponse:
        token = _token_from_metadata(context)
        if not token:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Missing token")

        try:
            payload = decode_token(token)
        except ValueError as exc:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, str(exc))

        exp = int(payload.get("exp", 0))
        now_ts = int(datetime.now(UTC).timestamp())
        ttl = max(exp - now_ts, 1)

        async for redis_conn in get_redis():
            await redis_conn.setex(f"blacklist:{token}", ttl, "1")
            await redis_conn.setex(
                f"token:invalidated:{payload['sub']}", ttl, str(now_ts)
            )

        return auth_pb2.LogoutResponse(message="Logged out successfully.")

    async def Refresh(
        self,
        request: auth_pb2.RefreshRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.TokenResponse:
        user_id = context.user_payload["sub"]
        async for redis_conn in get_redis():
            if await redis_conn.get(f"token:invalidated:{user_id}"):
                await context.abort(
                    grpc.StatusCode.UNAUTHENTICATED, "Session invalidated, please log in again"
                )

        token_data = {
            "sub": user_id,
            "role": context.user_payload["role"],
            "org_id": context.user_payload["org_id"],
        }
        access_token = create_access_token(
            data=token_data,
            expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
        )
        expires_in = settings.access_token_expire_minutes * 60
        return auth_pb2.TokenResponse(
            access_token=access_token, token_type="bearer", expires_in=expires_in  # noqa: S106
        )

    async def GetMe(
        self,
        request: auth_pb2.GetMeRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.UserProfile:
        async with AsyncSessionLocal() as db:
            user = await _get_user(db, context.user_payload["sub"])
        return _user_to_proto(user)

    async def SetupMFA(
        self,
        request: auth_pb2.SetupMFARequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.MFASetupResponse:
        async with AsyncSessionLocal() as db:
            user = await _get_user(db, context.user_payload["sub"])
            if user.mfa_enabled:
                await context.abort(grpc.StatusCode.ALREADY_EXISTS, "MFA already enabled")
            secret = pyotp.random_base32()
            user.mfa_secret = secret
            await db.commit()

        totp = pyotp.TOTP(secret)
        return auth_pb2.MFASetupResponse(
            provisioning_uri=totp.provisioning_uri(name=user.email, issuer_name="RWA Platform"),
            secret=secret,
        )

    async def EnableMFA(
        self,
        request: auth_pb2.MFAVerifyRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.MFAActionResponse:
        async with AsyncSessionLocal() as db:
            user = await _get_user(db, context.user_payload["sub"])
            if not user.mfa_secret:
                await context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Call SetupMFA first")
            if user.mfa_enabled:
                await context.abort(grpc.StatusCode.ALREADY_EXISTS, "MFA already enabled")
            if not pyotp.TOTP(user.mfa_secret).verify(request.code, valid_window=1):
                await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid TOTP code")
            user.mfa_enabled = True
            await db.commit()
        return auth_pb2.MFAActionResponse(message="MFA enabled.")

    async def DisableMFA(
        self,
        request: auth_pb2.MFAVerifyRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.MFAActionResponse:
        async with AsyncSessionLocal() as db:
            user = await _get_user(db, context.user_payload["sub"])
            if not user.mfa_enabled or not user.mfa_secret:
                await context.abort(grpc.StatusCode.FAILED_PRECONDITION, "MFA not enabled")
            if not pyotp.TOTP(user.mfa_secret).verify(request.code, valid_window=1):
                await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid TOTP code")
            user.mfa_enabled = False
            user.mfa_secret = None
            await db.commit()
        return auth_pb2.MFAActionResponse(message="MFA disabled.")

    async def ExportMyData(
        self,
        request: auth_pb2.ExportRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.UserDataExport:
        from sqlalchemy import or_
        user_id = UUID(context.user_payload["sub"])

        async with AsyncSessionLocal() as db:
            user = await _get_user(db, str(user_id))

            cr_res = (await db.execute(
                select(ComplianceRecord).where(ComplianceRecord.participant_id == user_id)
            )).scalars().all()
            compliance = [
                {"kyc_level": r.kyc_level, "kyc_status": r.kyc_status,
                 "aml_score": float(r.aml_score), "risk_category": r.risk_category,
                 "expires_at": r.expires_at.isoformat() if r.expires_at else None}
                for r in cr_res
            ]

            doc_res = (await db.execute(
                select(KYCDocument).where(KYCDocument.user_id == user_id)
            )).scalars().all()
            documents = [
                {"document_type": d.document_type, "issuing_country": d.issuing_country,
                 "verified": d.verified}
                for d in doc_res
            ]

            tx_res = (await db.execute(
                select(Transaction).where(or_(
                    Transaction.initiator_id == user_id,
                    Transaction.from_owner_id == user_id,
                    Transaction.to_owner_id == user_id,
                )).limit(500)
            )).scalars().all()
            transactions = [
                {"tx_ref": t.tx_ref, "tx_type": t.tx_type,
                 "amount": float(t.amount) if t.amount else None}
                for t in tx_res
            ]

        payload = {
            "user": {"id": str(user.id), "email": user.email,
                     "role": user.role, "org_id": str(user.org_id)},
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
        user_id = UUID(context.user_payload["sub"])
        now = datetime.now(UTC)

        async with AsyncSessionLocal() as db:
            user = await _get_user(db, str(user_id))
            user.email = f"deleted-{user_id}@anonymised.invalid"
            user.first_name = None
            user.last_name = None
            user.phone = None
            user.mfa_secret = None
            user.mfa_enabled = False
            user.is_active = False
            user.hashed_password = ""
            await db.execute(delete(KYCDocument).where(KYCDocument.user_id == user_id))
            await db.execute(
                update(ZKPCredential)
                .where(ZKPCredential.user_id == user_id, ~ZKPCredential.revoked)
                .values(revoked=True, revoked_at=now, revoked_reason="gdpr_erasure")
            )
            await db.commit()

        async for redis_conn in get_redis():
            await redis_conn.setex(
                f"token:invalidated:{user_id}", 86400 * 30, str(now.timestamp())
            )

        return auth_pb2.DeleteResponse(message="Account anonymised (GDPR Art. 17).")


# ---------------------------------------------------------------------------

async def _get_user(db: AsyncSession, user_id: str) -> User:
    stmt = select(User).where(User.id == UUID(user_id))
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user:
        raise ValueError(f"User {user_id} not found")
    return user


def _user_to_proto(user: User) -> auth_pb2.UserProfile:
    return auth_pb2.UserProfile(
        id=str(user.id),
        email=user.email or "",
        first_name=user.first_name or "",
        last_name=user.last_name or "",
        role=user.role or "",
        org_id=str(user.org_id) if user.org_id else "",
        mfa_enabled=bool(user.mfa_enabled),
        created_at=user.created_at.isoformat() if user.created_at else "",
        last_login=user.last_login.isoformat() if user.last_login else "",
    )


def _token_from_metadata(context: grpc.aio.ServicerContext) -> str | None:
    for key, value in context.invocation_metadata():
        if key == "authorization" and value.startswith("Bearer "):
            return value[len("Bearer "):]
    return None
