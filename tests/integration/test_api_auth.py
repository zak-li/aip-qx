from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import BANK01_ORG_ID, THOMAS_USER_ID


async def test_login_thomas_martin_returns_valid_jwt(
    test_client: AsyncClient,
    async_session: AsyncSession, test_org, test_user_thomas,
):
    resp = await test_client.post(
        "/api/v1/auth/login",
        json={"email": "thomas.martin@bank01.fr", "password": "Passw0rd!"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"

async def test_login_wrong_password_returns_401(
    test_client: AsyncClient,
    async_session: AsyncSession, test_org, test_user_thomas,
):
    resp = await test_client.post(
        "/api/v1/auth/login",
        json={"email": "thomas.martin@bank01.fr", "password": "WrongPass!"},
    )
    assert resp.status_code in (400, 401)

async def test_login_unknown_email_returns_401(
    test_client: AsyncClient,
    async_session: AsyncSession, test_org, test_user_thomas,
):
    resp = await test_client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@nowhere.com", "password": "Passw0rd!"},
    )
    assert resp.status_code in (400, 401)

async def test_get_me_with_valid_token_returns_profile(
    test_client: AsyncClient, token_thomas_martin: str,
    async_session: AsyncSession, test_org, test_user_thomas,
):
    resp = await test_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token_thomas_martin}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "thomas.martin@bank01.fr"
    assert body["role"] == "EMETTEUR"

async def test_get_me_with_expired_token_returns_401(
    test_client: AsyncClient, token_expired: str,
):
    resp = await test_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token_expired}"},
    )
    assert resp.status_code == 401

async def test_logout_blacklists_token_in_redis(
    test_client: AsyncClient, token_thomas_martin: str,
    async_session: AsyncSession, test_org, test_user_thomas,
):
    resp_logout = await test_client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {token_thomas_martin}"},
    )
    assert resp_logout.status_code == 200

    resp_me = await test_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token_thomas_martin}"},
    )
    assert resp_me.status_code == 401

async def test_regulateur_can_access_freeze_endpoint(
    test_client: AsyncClient, token_sophie_lambert: str,
    async_session: AsyncSession, test_org, test_user_thomas, test_amf_org, test_user_sophie,
):
    from datetime import date
    from decimal import Decimal

    from backend.features.assets.models import Asset
    asset = Asset(
        asset_id="RWA-OBL-AUTHFR-001",
        isin="FR0014004L86",
        asset_type="OBLIGATION",
        asset_name="Auth Freeze Test",
        issuer_org_id=BANK01_ORG_ID,
        current_owner_id=THOMAS_USER_ID,
        nominal_value=Decimal("10000000"),
        current_value=Decimal("10000000"),
        currency="EUR",
        status="ACTIF",
        issuance_date=date(2026, 1, 15),
    )
    async_session.add(asset)
    await async_session.flush()

    payload = {
        "asset_id": "RWA-OBL-AUTHFR-001",
        "reason": "Test regulateur authorization freeze check",
        "regulatory_ref": "REG01-INV-2026-001",
    }
    resp = await test_client.post(
        "/api/v1/assets/freeze",
        json=payload,
        headers={"Authorization": f"Bearer {token_sophie_lambert}"},
    )
    assert resp.status_code != 403

async def test_trader_cannot_access_freeze_endpoint(
    test_client: AsyncClient, token_james_wilson: str,
):
    payload = {
        "asset_id": "RWA-OBL-BANK01-2025-001",
        "reason": "Trader tentative gel non autorise test",
        "regulatory_ref": "REG01-INV-2026-001",
    }
    resp = await test_client.post(
        "/api/v1/assets/freeze",
        json=payload,
        headers={"Authorization": f"Bearer {token_james_wilson}"},
    )
    assert resp.status_code in (401, 403)
