"""Auth router — Keycloak OIDC SSO.

Authentication flow:
  1. GET  /login      — redirect the browser to Keycloak (PKCE + state).
  2. GET  /callback   — receive the authorization code, exchange for tokens,
                        look up / create the user, set httpOnly cookies.
  3. POST /logout     — clear cookies and revoke the Keycloak session.
  4. POST /refresh    — exchange the refresh-token cookie for a new access token.
  5. GET  /me         — current user profile (authenticated).

GDPR:
  6. GET  /me/export  — GDPR Art. 15 personal-data export.
  7. DELETE /me       — GDPR Art. 17 right to erasure (anonymisation).
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from redis.asyncio import Redis
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.core.auth_cookies import (
    REFRESH_COOKIE,
    clear_session_cookies,
    issue_csrf_token,
    set_session_cookies,
)
from core.core.oidc import (
    build_authorization_url,
    delete_keycloak_user,
    exchange_code,
    extract_role,
    generate_pkce_pair,
    generate_state,
    refresh_access_token,
    revoke_session,
    validate_token,
)
from core.core.redis_client import get_redis
from core.dependencies import get_current_user, get_db
from core.features.auth.models import User
from core.features.auth.schemas import OIDCTokenResponse, UserProfile
from core.features.compliance.models import AuditLog, ComplianceRecord, KYCDocument
from core.features.transactions.models import Transaction
from core.features.zkp.models import ZKPCredential

logger = logging.getLogger(__name__)

router = APIRouter()

# Redis TTL for PKCE state entries (5 minutes — enough for the browser round-trip)
_STATE_TTL = 300


# ─────────────────────────── OIDC flow ───────────────────────────────────────

@router.get("/login")
async def oidc_login(
    redirect_after: str = Query(default="/", description="Frontend path to redirect to after login"),
    redis: Redis = Depends(get_redis),
) -> RedirectResponse:
    """Redirect the browser to Keycloak's login page (PKCE, authorization_code flow)."""
    state = generate_state()
    code_verifier, code_challenge = generate_pkce_pair()

    # Store (code_verifier, redirect_after) under the state key so we can
    # retrieve it at callback time.
    await redis.setex(
        f"oidc:state:{state}",
        _STATE_TTL,
        f"{code_verifier}|{redirect_after}",
    )

    auth_url = build_authorization_url(
        redirect_uri=settings.keycloak_callback_url,
        state=state,
        code_challenge=code_challenge,
    )
    return RedirectResponse(url=auth_url, status_code=302)


@router.get("/callback")
async def oidc_callback(
    code: str = Query(...),
    state: str = Query(...),
    response: Response = None,
    redis: Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
) -> OIDCTokenResponse:
    """Handle the Keycloak redirect, exchange code, and establish a session."""
    # Validate CSRF state
    state_value = await redis.get(f"oidc:state:{state}")
    if not state_value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired state parameter.",
        )
    await redis.delete(f"oidc:state:{state}")

    raw = state_value if isinstance(state_value, str) else state_value.decode()
    code_verifier, _redirect_after = raw.split("|", 1)

    # Exchange authorization code for tokens
    try:
        token_set = await exchange_code(
            code=code,
            redirect_uri=settings.keycloak_callback_url,
            code_verifier=code_verifier,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc

    access_token: str = token_set["access_token"]
    refresh_token: str = token_set.get("refresh_token", "")
    expires_in: int = token_set.get("expires_in", 900)
    refresh_expires_in: int = token_set.get("refresh_expires_in", 0)

    # Validate and decode the access token
    try:
        payload = await validate_token(access_token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc

    keycloak_sub: str = payload["sub"]
    email: str = payload.get("email", "")
    role_from_kc: str | None = extract_role(payload)

    # Find or create the user record in our DB
    await _upsert_user(db, keycloak_sub, email, role_from_kc)

    # Issue session cookies
    csrf = issue_csrf_token()
    set_session_cookies(response, access_token, refresh_token, csrf, expires_in)

    return OIDCTokenResponse(
        access_token=access_token,
        token_type="bearer",  # noqa: S106
        expires_in=expires_in,
        refresh_expires_in=refresh_expires_in,
    )


@router.post("/logout", status_code=200)
async def logout(
    request: Request,
    response: Response,
    redis: Redis = Depends(get_redis),
) -> dict[str, str]:
    """Invalidate the session: clear cookies and revoke the Keycloak session."""
    refresh_token_value = request.cookies.get(REFRESH_COOKIE, "")

    # Blacklist the current access token's jti in Redis
    payload = getattr(request.state, "token_payload", None)
    if payload:
        jti: str = payload.get("jti", "")
        exp: int = int(payload.get("exp", 0))
        now_ts: int = int(datetime.now(UTC).timestamp())
        ttl = max(exp - now_ts, 1)
        if jti:
            await redis.setex(f"oidc:blacklist:{jti}", ttl, "1")

        keycloak_sub: str = payload.get("sub", "")
        iat: int = int(payload.get("iat", 0))
        if keycloak_sub:
            await redis.setex(f"oidc:invalidated:{keycloak_sub}", ttl, str(iat))

    # Back-channel logout on Keycloak (best-effort)
    if refresh_token_value:
        try:
            await revoke_session(refresh_token_value)
        except Exception:
            logger.warning("Keycloak back-channel logout failed — proceeding anyway")

    clear_session_cookies(response)
    return {"message": "Déconnexion réussie."}


@router.post("/refresh", response_model=OIDCTokenResponse)
async def refresh(
    request: Request,
    response: Response,
) -> OIDCTokenResponse:
    """Exchange the refresh-token cookie for a new access token."""
    refresh_token_value = request.cookies.get(REFRESH_COOKIE, "")
    if not refresh_token_value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token cookie found.",
        )

    try:
        token_set = await refresh_access_token(refresh_token_value)
    except ValueError as exc:
        clear_session_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc

    access_token: str = token_set["access_token"]
    new_refresh: str = token_set.get("refresh_token", refresh_token_value)
    expires_in: int = token_set.get("expires_in", 900)
    refresh_expires_in: int = token_set.get("refresh_expires_in", 0)

    csrf = issue_csrf_token()
    set_session_cookies(response, access_token, new_refresh, csrf, expires_in)

    return OIDCTokenResponse(
        access_token=access_token,
        token_type="bearer",  # noqa: S106
        expires_in=expires_in,
        refresh_expires_in=refresh_expires_in,
    )


@router.get("/me", response_model=UserProfile)
async def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    return current_user


# ─────────────────────────── GDPR ────────────────────────────────────────────

@router.get("/me/export", tags=["GDPR"])
async def export_my_data(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """GDPR Art. 15 — Export all personal data held for the authenticated user."""
    from sqlalchemy import or_

    cr_res = await db.execute(
        select(ComplianceRecord).where(ComplianceRecord.participant_id == current_user.id)
    )
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

    doc_res = await db.execute(
        select(KYCDocument).where(KYCDocument.user_id == current_user.id)
    )
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

    log_res = await db.execute(
        select(AuditLog)
        .where(AuditLog.user_id == current_user.id)
        .order_by(AuditLog.created_at.desc())
        .limit(100)
    )
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

    tx_res = await db.execute(
        select(Transaction)
        .where(
            or_(
                Transaction.initiator_id == current_user.id,
                Transaction.from_owner_id == current_user.id,
                Transaction.to_owner_id == current_user.id,
            )
        )
        .order_by(Transaction.created_at.desc())
        .limit(500)
    )
    transactions = [
        {
            "tx_ref": t.tx_ref,
            "fabric_tx_id": t.fabric_tx_id,
            "tx_type": t.tx_type,
            "amount": float(t.amount) if t.amount is not None else None,
            "currency": t.currency,
            "role": (
                "initiator"
                if t.initiator_id == current_user.id
                else "sender"
                if t.from_owner_id == current_user.id
                else "recipient"
            ),
            "timestamp": t.created_at.isoformat() if t.created_at else None,
        }
        for t in tx_res.scalars().all()
    ]

    zkp_res = await db.execute(
        select(ZKPCredential).where(ZKPCredential.user_id == current_user.id)
    )
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

    return JSONResponse(
        content={
            "user": {
                "id": str(current_user.id),
                "email": current_user.email,
                "first_name": current_user.first_name,
                "last_name": current_user.last_name,
                "role": current_user.role,
                "org_id": str(current_user.org_id),
                "keycloak_sub": current_user.keycloak_sub,
                "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
                "last_login": current_user.last_login.isoformat() if current_user.last_login else None,
            },
            "compliance_records": compliance,
            "kyc_documents": documents,
            "audit_logs": audit,
            "transactions": transactions,
            "zkp_credentials": zkp_credentials,
        }
    )


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT, tags=["GDPR"])
async def delete_my_account(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> None:
    """GDPR Art. 17 — Right to erasure.

    Anonymises PII in our DB, revokes ZKP credentials, and deletes the user
    from Keycloak.  Audit logs and compliance records are retained with the
    user ID intact (they no longer link to PII after anonymisation).
    """
    user_id = current_user.id
    keycloak_sub = current_user.keycloak_sub or ""

    current_user.email = f"deleted-{user_id}@anonymised.invalid"
    current_user.first_name = None
    current_user.last_name = None
    current_user.phone = None
    current_user.keycloak_sub = None
    current_user.is_active = False

    await db.execute(delete(KYCDocument).where(KYCDocument.user_id == user_id))

    now = datetime.now(UTC)
    await db.execute(
        update(ZKPCredential)
        .where(ZKPCredential.user_id == user_id, ~ZKPCredential.revoked)
        .values(revoked=True, revoked_at=now, revoked_reason="gdpr_erasure")
    )
    await db.commit()

    # Invalidate all active sessions for this user
    await redis.setex(f"oidc:invalidated:{keycloak_sub}", 86400 * 30, str(int(now.timestamp())))

    # Remove user from Keycloak (best-effort — our DB record is already anonymised)
    if keycloak_sub:
        try:
            await delete_keycloak_user(keycloak_sub)
        except Exception:
            logger.warning("Could not delete Keycloak user %s — already removed?", keycloak_sub)


# ─────────────────────────── helpers ─────────────────────────────────────────

async def _upsert_user(
    db: AsyncSession,
    keycloak_sub: str,
    email: str,
    role_from_kc: str | None,
) -> User:
    """Find an existing user by keycloak_sub (or by email for first-time SSO login),
    sync role from Keycloak if it has changed, and persist last_login."""
    user: User | None = (
        await db.execute(select(User).where(User.keycloak_sub == keycloak_sub))
    ).scalar_one_or_none()

    if user is None and email:
        # First-time SSO login — link Keycloak sub to an existing account by email.
        user = (
            await db.execute(
                select(User).where(User.email == email, User.is_active.is_(True))
            )
        ).scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "No active account found for this Keycloak identity. "
                "Contact your administrator to provision an account."
            ),
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive.",
        )

    # Link and sync
    if user.keycloak_sub != keycloak_sub:
        user.keycloak_sub = keycloak_sub
    if role_from_kc and user.role != role_from_kc:
        user.role = role_from_kc
    user.last_login = datetime.now(UTC)
    await db.commit()

    return user
