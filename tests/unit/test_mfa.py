import uuid
from datetime import timedelta

import pyotp
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.security import create_access_token, hash_password
from backend.features.auth.models import Organization, User
from tests.conftest import BNP_ORG_ID, THOMAS_USER_ID


@pytest.fixture
async def test_user_mfa(async_session: AsyncSession, test_org: Organization) -> User:
    user = User(
        id=THOMAS_USER_ID,
        org_id=BNP_ORG_ID,
        email="thomas.mfa@bank01.fr",
        hashed_password=hash_password("Passw0rd!"),
        first_name="Thomas",
        last_name="MFA",
        role="EMETTEUR",
        msp_id="BANK01MSP",
        is_active=True,
        mfa_enabled=False,
        mfa_secret=None,
    )
    await async_session.merge(user)
    await async_session.flush()
    return user


@pytest.fixture
def token_mfa_user() -> str:
    payload = {"sub": str(THOMAS_USER_ID), "role": "EMETTEUR", "org_id": str(BNP_ORG_ID)}
    return create_access_token(payload, expires_delta=timedelta(hours=24))


async def test_mfa_setup_returns_provisioning_uri(
    test_client, token_mfa_user, test_user_mfa, async_session
):
    response = await test_client.post(
        "/api/v1/auth/mfa/setup",
        headers={"Authorization": f"Bearer {token_mfa_user}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "provisioning_uri" in data
    assert "secret" in data
    assert "otpauth://totp/" in data["provisioning_uri"]
    assert "RWA%20Platform" in data["provisioning_uri"]


async def test_mfa_setup_fails_if_already_enabled(
    async_session: AsyncSession, test_org, token_mfa_user, test_client
):
    user = User(
        id=uuid.UUID("20000000-0000-0000-0000-000000000099"),
        org_id=BNP_ORG_ID,
        email="already.mfa@bank01.fr",
        hashed_password=hash_password("Passw0rd!"),
        role="EMETTEUR",
        is_active=True,
        mfa_enabled=True,
        mfa_secret=pyotp.random_base32(),
    )
    await async_session.merge(user)
    await async_session.flush()

    token = create_access_token(
        {"sub": str(user.id), "role": "EMETTEUR", "org_id": str(BNP_ORG_ID)},
        expires_delta=timedelta(hours=1),
    )
    response = await test_client.post(
        "/api/v1/auth/mfa/setup",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


async def test_mfa_enable_with_valid_code(
    async_session: AsyncSession, test_org, test_client
):
    secret = pyotp.random_base32()
    user = User(
        id=uuid.UUID("20000000-0000-0000-0000-000000000010"),
        org_id=BNP_ORG_ID,
        email="enable.mfa@bank01.fr",
        hashed_password=hash_password("Passw0rd!"),
        role="EMETTEUR",
        is_active=True,
        mfa_enabled=False,
        mfa_secret=secret,
    )
    await async_session.merge(user)
    await async_session.flush()

    token = create_access_token(
        {"sub": str(user.id), "role": "EMETTEUR", "org_id": str(BNP_ORG_ID)},
        expires_delta=timedelta(hours=1),
    )
    totp = pyotp.TOTP(secret)
    response = await test_client.post(
        "/api/v1/auth/mfa/enable",
        headers={"Authorization": f"Bearer {token}"},
        json={"code": totp.now()},
    )
    assert response.status_code == 200
    assert "activé" in response.json()["message"]


async def test_mfa_enable_with_invalid_code(
    async_session: AsyncSession, test_org, test_client
):
    secret = pyotp.random_base32()
    user = User(
        id=uuid.UUID("20000000-0000-0000-0000-000000000011"),
        org_id=BNP_ORG_ID,
        email="invalid.mfa@bank01.fr",
        hashed_password=hash_password("Passw0rd!"),
        role="EMETTEUR",
        is_active=True,
        mfa_enabled=False,
        mfa_secret=secret,
    )
    await async_session.merge(user)
    await async_session.flush()

    token = create_access_token(
        {"sub": str(user.id), "role": "EMETTEUR", "org_id": str(BNP_ORG_ID)},
        expires_delta=timedelta(hours=1),
    )
    response = await test_client.post(
        "/api/v1/auth/mfa/enable",
        headers={"Authorization": f"Bearer {token}"},
        json={"code": "000000"},
    )
    assert response.status_code == 400


async def test_login_returns_mfa_required_flag_when_mfa_enabled(
    async_session: AsyncSession, test_org, test_client
):
    secret = pyotp.random_base32()
    user = User(
        id=uuid.UUID("20000000-0000-0000-0000-000000000020"),
        org_id=BNP_ORG_ID,
        email="mfa.login@bank01.fr",
        hashed_password=hash_password("Passw0rd!"),
        role="EMETTEUR",
        is_active=True,
        mfa_enabled=True,
        mfa_secret=secret,
    )
    await async_session.merge(user)
    await async_session.flush()

    response = await test_client.post(
        "/api/v1/auth/login",
        json={"email": "mfa.login@bank01.fr", "password": "Passw0rd!"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["mfa_required"] is True
    assert data["access_token"] == ""


async def test_login_with_valid_mfa_code_succeeds(
    async_session: AsyncSession, test_org, test_client
):
    secret = pyotp.random_base32()
    user = User(
        id=uuid.UUID("20000000-0000-0000-0000-000000000021"),
        org_id=BNP_ORG_ID,
        email="mfa.fulllogin@bank01.fr",
        hashed_password=hash_password("Passw0rd!"),
        role="EMETTEUR",
        is_active=True,
        mfa_enabled=True,
        mfa_secret=secret,
    )
    await async_session.merge(user)
    await async_session.flush()

    totp = pyotp.TOTP(secret)
    response = await test_client.post(
        "/api/v1/auth/login",
        json={
            "email": "mfa.fulllogin@bank01.fr",
            "password": "Passw0rd!",
            "mfa_code": totp.now(),
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["mfa_required"] is False
    assert len(data["access_token"]) > 0


async def test_login_with_invalid_mfa_code_returns_401(
    async_session: AsyncSession, test_org, test_client
):
    secret = pyotp.random_base32()
    user = User(
        id=uuid.UUID("20000000-0000-0000-0000-000000000022"),
        org_id=BNP_ORG_ID,
        email="mfa.badcode@bank01.fr",
        hashed_password=hash_password("Passw0rd!"),
        role="EMETTEUR",
        is_active=True,
        mfa_enabled=True,
        mfa_secret=secret,
    )
    await async_session.merge(user)
    await async_session.flush()

    response = await test_client.post(
        "/api/v1/auth/login",
        json={
            "email": "mfa.badcode@bank01.fr",
            "password": "Passw0rd!",
            "mfa_code": "000000",
        },
    )
    assert response.status_code == 401


async def test_mfa_disable_with_valid_code(
    async_session: AsyncSession, test_org, test_client
):
    secret = pyotp.random_base32()
    user = User(
        id=uuid.UUID("20000000-0000-0000-0000-000000000030"),
        org_id=BNP_ORG_ID,
        email="disable.mfa@bank01.fr",
        hashed_password=hash_password("Passw0rd!"),
        role="EMETTEUR",
        is_active=True,
        mfa_enabled=True,
        mfa_secret=secret,
    )
    await async_session.merge(user)
    await async_session.flush()

    token = create_access_token(
        {"sub": str(user.id), "role": "EMETTEUR", "org_id": str(BNP_ORG_ID)},
        expires_delta=timedelta(hours=1),
    )
    totp = pyotp.TOTP(secret)
    response = await test_client.post(
        "/api/v1/auth/mfa/disable",
        headers={"Authorization": f"Bearer {token}"},
        json={"code": totp.now()},
    )
    assert response.status_code == 200
    assert "désactivé" in response.json()["message"]
