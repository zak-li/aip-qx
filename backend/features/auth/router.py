import logging
from datetime import datetime, timedelta, UTC

import pyotp
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.core.auth_cookies import (
    clear_session_cookies,
    issue_csrf_token,
    set_session_cookies,
)
from backend.core.security import create_access_token, decode_token, verify_password
from backend.dependencies import get_current_user, get_db, get_redis
from backend.features.auth.models import User
from backend.features.compliance.models import ComplianceRecord, KYCDocument, AuditLog
from backend.features.transactions.models import Transaction
from backend.features.zkp.models import ZKPCredential
from backend.features.auth.schemas import (
    LoginRequest,
    MFASetupResponse,
    MFAVerifyRequest,
    TokenResponse,
    UserProfile,
)

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 15

@router.post("/login", response_model=TokenResponse)
async def login_access_token(
    request: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    stmt = select(User).where(User.email == request.email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not verify_password(request.password, user.hashed_password):
        if user:
            user.failed_login_count = (user.failed_login_count or 0) + 1
            if user.failed_login_count >= MAX_FAILED_ATTEMPTS:
                user.locked_until = datetime.now(UTC) + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
                logger.warning(f"Compte verrouillé pour {user.email} après {user.failed_login_count} tentatives")
            await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.is_locked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Compte verrouillé jusqu'à {user.locked_until}",
        )

    if user.mfa_enabled and user.mfa_secret:
        if not request.mfa_code:
            return TokenResponse(
                access_token="",
                token_type="bearer",
                expires_in=0,
                mfa_required=True,
            )
        totp = pyotp.TOTP(user.mfa_secret)
        if not totp.verify(request.mfa_code, valid_window=1):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Code MFA invalide",
                headers={"WWW-Authenticate": "Bearer"},
            )

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login = datetime.now(UTC)
    await db.commit()

    token_data = {
        "sub": str(user.id),
        "role": user.role,
        "org_id": str(user.org_id),
    }

    access_token = create_access_token(
        data=token_data,
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )

    expires_in = settings.access_token_expire_minutes * 60
    set_session_cookies(response, access_token, issue_csrf_token(), expires_in)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=expires_in,
        mfa_required=False,
    )

@router.get("/me", response_model=UserProfile)
async def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    return current_user

@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    redis_conn: Redis = Depends(get_redis),
) -> dict[str, str]:
    # Pull the token from the same place auth middleware did — header or cookie.
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
    else:
        from backend.core.auth_cookies import SESSION_COOKIE
        token = request.cookies.get(SESSION_COOKIE) or ""

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing session token")

    try:
        payload = decode_token(token)
    except ValueError:
        clear_session_cookies(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    exp = int(payload.get("exp", 0))
    now = int(datetime.now(UTC).timestamp())
    ttl = max(exp - now, 1)

    await redis_conn.setex(f"blacklist:{token}", ttl, "1")
    await redis_conn.setex(f"token:invalidated:{current_user.id}", ttl, str(now))

    clear_session_cookies(response)
    return {"message": "Déconnexion réussie."}

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    response: Response,
    current_user: User = Depends(get_current_user),
    redis_conn: Redis = Depends(get_redis),
) -> TokenResponse:
    invalidated = await redis_conn.get(f"token:invalidated:{current_user.id}")
    if invalidated:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session invalidée, reconnexion requise.")

    token_data = {
        "sub": str(current_user.id),
        "role": current_user.role,
        "org_id": str(current_user.org_id),
    }

    access_token = create_access_token(
        data=token_data,
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )

    expires_in = settings.access_token_expire_minutes * 60
    set_session_cookies(response, access_token, issue_csrf_token(), expires_in)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=expires_in,
    )

@router.post("/mfa/setup", response_model=MFASetupResponse)
async def setup_mfa(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MFASetupResponse:
    if current_user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA déjà activé. Désactivez-le d'abord.",
        )

    secret = pyotp.random_base32()
    current_user.mfa_secret = secret
    await db.commit()

    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(
        name=current_user.email,
        issuer_name="RWA Platform",
    )

    return MFASetupResponse(provisioning_uri=provisioning_uri, secret=secret)

@router.post("/mfa/enable")
async def enable_mfa(
    body: MFAVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    if not current_user.mfa_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Aucun secret MFA configuré. Appelez /mfa/setup d'abord.",
        )
    if current_user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA déjà activé.",
        )

    totp = pyotp.TOTP(current_user.mfa_secret)
    if not totp.verify(body.code, valid_window=1):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Code TOTP invalide.",
        )

    current_user.mfa_enabled = True
    await db.commit()
    return {"message": "MFA activé avec succès."}

@router.post("/mfa/disable")
async def disable_mfa(
    body: MFAVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    if not current_user.mfa_enabled or not current_user.mfa_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA non activé.",
        )

    totp = pyotp.TOTP(current_user.mfa_secret)
    if not totp.verify(body.code, valid_window=1):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Code TOTP invalide.",
        )

    current_user.mfa_enabled = False
    current_user.mfa_secret = None
    await db.commit()
    return {"message": "MFA désactivé."}


# ---------------------------------------------------------------------------
# GDPR — Right of Access (Article 15) & Right to Erasure (Article 17)
# ---------------------------------------------------------------------------

@router.get("/me/export", tags=["GDPR"])
async def export_my_data(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """GDPR Art. 15 — Export all personal data held for the authenticated user."""
    # Compliance records
    cr_stmt = select(ComplianceRecord).where(ComplianceRecord.participant_id == current_user.id)
    cr_res = await db.execute(cr_stmt)
    compliance = [
        {
            "kyc_level": r.kyc_level,
            "kyc_status": r.kyc_status,
            "aml_score": float(r.aml_score),
            "risk_category": r.risk_category,
            "expires_at": r.expires_at.isoformat() if r.expires_at else None,
        }
        for r in cr_res.scalars().all()
    ]

    # KYC documents (metadata only — no file contents)
    doc_stmt = select(KYCDocument).where(KYCDocument.user_id == current_user.id)
    doc_res = await db.execute(doc_stmt)
    documents = [
        {
            "document_type": d.document_type,
            "issuing_country": d.issuing_country,
            "issued_date": str(d.issued_date) if d.issued_date else None,
            "expiry_date": str(d.expiry_date) if d.expiry_date else None,
            "verified": d.verified,
        }
        for d in doc_res.scalars().all()
    ]

    # Audit logs (last 100 entries)
    log_stmt = (
        select(AuditLog)
        .where(AuditLog.user_id == current_user.id)
        .order_by(AuditLog.created_at.desc())
        .limit(100)
    )
    log_res = await db.execute(log_stmt)
    audit = [
        {
            "endpoint": lg.endpoint,
            "method": lg.http_method,
            "response_code": lg.response_code,
            "ip_address": lg.ip_address,
            "timestamp": lg.created_at.isoformat() if lg.created_at else None,
        }
        for lg in log_res.scalars().all()
    ]

    # Transactions (Article 15 — also "personal data" because the user appears as
    # initiator / from_owner / to_owner; the financial detail is part of the
    # data we hold on them).
    from sqlalchemy import or_
    tx_stmt = (
        select(Transaction)
        .where(or_(
            Transaction.initiator_id == current_user.id,
            Transaction.from_owner_id == current_user.id,
            Transaction.to_owner_id == current_user.id,
        ))
        .order_by(Transaction.created_at.desc())
        .limit(500)
    )
    tx_res = await db.execute(tx_stmt)
    transactions = [
        {
            "tx_ref": t.tx_ref,
            "fabric_tx_id": t.fabric_tx_id,
            "tx_type": t.tx_type,
            "amount": float(t.amount) if t.amount is not None else None,
            "currency": t.currency,
            "role": (
                "initiator" if t.initiator_id == current_user.id
                else "sender" if t.from_owner_id == current_user.id
                else "recipient"
            ),
            "timestamp": t.created_at.isoformat() if t.created_at else None,
        }
        for t in tx_res.scalars().all()
    ]

    # ZKP credentials issued for this user
    zkp_stmt = select(ZKPCredential).where(ZKPCredential.user_id == current_user.id)
    zkp_res = await db.execute(zkp_stmt)
    zkp_credentials = [
        {
            "credential_id": str(c.id),
            "kyc_level": c.kyc_level,
            "issued_at": c.issued_at.isoformat() if c.issued_at else None,
            "expires_at": c.expires_at.isoformat() if c.expires_at else None,
            "revoked": c.revoked,
        }
        for c in zkp_res.scalars().all()
    ]

    return JSONResponse(content={
        "user": {
            "id": str(current_user.id),
            "email": current_user.email,
            "first_name": current_user.first_name,
            "last_name": current_user.last_name,
            "role": current_user.role,
            "org_id": str(current_user.org_id),
            "mfa_enabled": current_user.mfa_enabled,
            "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
            "last_login": current_user.last_login.isoformat() if current_user.last_login else None,
        },
        "compliance_records": compliance,
        "kyc_documents": documents,
        "audit_logs": audit,
        "transactions": transactions,
        "zkp_credentials": zkp_credentials,
    })


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT, tags=["GDPR"])
async def delete_my_account(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis_conn: Redis = Depends(get_redis),
) -> None:
    """GDPR Art. 17 — Right to erasure.

    Anonymises personal data instead of hard-deleting, to preserve the integrity
    of the financial audit trail (regulatory obligation under MiCA / AML directives).
    The user's email, name, and MFA secret are wiped; the account is deactivated.
    Audit logs and compliance records are retained with the user ID intact
    (they no longer link to PII after anonymisation).
    """
    user_id = current_user.id

    # Anonymise PII on the user record
    current_user.email = f"deleted-{user_id}@anonymised.invalid"
    current_user.first_name = None
    current_user.last_name = None
    current_user.phone = None
    current_user.mfa_secret = None
    current_user.mfa_enabled = False
    current_user.is_active = False
    current_user.hashed_password = ""

    # Hard-delete KYC documents (personal identity papers)
    await db.execute(delete(KYCDocument).where(KYCDocument.user_id == user_id))

    # Revoke any ZKP credential issued to this user — the cryptographic claim
    # is itself a piece of personal data that must not remain usable.
    from sqlalchemy import update
    now = datetime.now(UTC)
    await db.execute(
        update(ZKPCredential)
        .where(ZKPCredential.user_id == user_id, ZKPCredential.revoked == False)
        .values(revoked=True, revoked_at=now, revoked_reason="gdpr_erasure")
    )

    await db.commit()

    # Invalidate all active sessions for this user
    await redis_conn.setex(f"token:invalidated:{user_id}", 86400 * 30, str(now.timestamp()))
