from datetime import date
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.features.assets.models import Asset
from tests.conftest import BANK01_ORG_ID, THOMAS_USER_ID


async def test_post_tokenize_with_emetteur_token_returns_201(
    test_client: AsyncClient, token_thomas_martin: str,
    async_session: AsyncSession, test_org, test_user_thomas,
):
    payload = {
        "asset_id": "RWA-OBL-TEST-2026-001",
        "isin": "FR0014004L86",
        "asset_type": "OBLIGATION",
        "asset_name": "Test Bond API 2026",
        "issuer_lei": "R0MUWSFPU8MPRO8K5P83",
        "nominal_value": 50000000,
        "currency": "EUR",
        "issuance_date": "2026-01-15",
        "justification": "Tokenisation test integration API assets",
    }
    resp = await test_client.post(
        "/api/v1/assets/tokenize",
        json=payload,
        headers={"Authorization": f"Bearer {token_thomas_martin}"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "asset_id" in body
    assert body.get("fabric_tx_id") is not None

async def test_post_tokenize_without_token_returns_401(test_client: AsyncClient):
    payload = {
        "asset_id": "RWA-OBL-TEST-2026-002",
        "isin": "FR0014004L86",
        "asset_type": "OBLIGATION",
        "asset_name": "Test Bond No Auth",
        "issuer_lei": "R0MUWSFPU8MPRO8K5P83",
        "nominal_value": 10000000,
        "currency": "EUR",
        "issuance_date": "2026-01-15",
        "justification": "Tentative sans authentification unitaire",
    }
    resp = await test_client.post("/api/v1/assets/tokenize", json=payload)
    assert resp.status_code == 401

async def test_post_tokenize_with_trader_token_returns_403(
    test_client: AsyncClient, token_james_wilson: str,
):
    payload = {
        "asset_id": "RWA-OBL-TEST-2026-003",
        "isin": "FR0014004L86",
        "asset_type": "OBLIGATION",
        "asset_name": "Test Bond Trader Denied",
        "issuer_lei": "R0MUWSFPU8MPRO8K5P83",
        "nominal_value": 5000000,
        "currency": "EUR",
        "issuance_date": "2026-01-15",
        "justification": "Tentative trader non autorise unitaire",
    }
    resp = await test_client.post(
        "/api/v1/assets/tokenize",
        json=payload,
        headers={"Authorization": f"Bearer {token_james_wilson}"},
    )
    assert resp.status_code in (401, 403)

async def test_post_freeze_with_regulateur_token_returns_200(
    test_client: AsyncClient, token_sophie_lambert: str,
    async_session: AsyncSession, test_org, test_user_thomas, test_amf_org, test_user_sophie,
):
    asset = Asset(
        asset_id="RWA-OBL-FREEZE-API-001",
        isin="FR0014004L86",
        asset_type="OBLIGATION",
        asset_name="Freeze API Test",
        issuer_org_id=BANK01_ORG_ID,
        current_owner_id=THOMAS_USER_ID,
        nominal_value=Decimal("20000000"),
        current_value=Decimal("20000000"),
        currency="EUR",
        status="ACTIF",
        issuance_date=date(2026, 1, 15),
    )
    async_session.add(asset)
    await async_session.flush()

    payload = {
        "asset_id": "RWA-OBL-FREEZE-API-001",
        "reason": "Investigation MIFID II art.69 reglementaire test",
        "regulatory_ref": "REG01-INV-2026-001",
    }
    resp = await test_client.post(
        "/api/v1/assets/freeze",
        json=payload,
        headers={"Authorization": f"Bearer {token_sophie_lambert}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "GELE"

async def test_post_freeze_with_emetteur_token_returns_403(
    test_client: AsyncClient, token_thomas_martin: str,
    async_session: AsyncSession, test_org, test_user_thomas,
):
    payload = {
        "asset_id": "RWA-OBL-BANK01-2025-001",
        "reason": "Emetteur tentative gel non autorisee test",
        "regulatory_ref": "REG01-INV-2026-001",
    }
    resp = await test_client.post(
        "/api/v1/assets/freeze",
        json=payload,
        headers={"Authorization": f"Bearer {token_thomas_martin}"},
    )
    assert resp.status_code == 403

async def test_post_transfer_on_frozen_asset_returns_409(
    test_client: AsyncClient, token_thomas_martin: str,
    async_session: AsyncSession, test_org, test_user_thomas,
):
    asset = Asset(
        asset_id="RWA-OBL-BANK01-2025-001",
        isin="FR0014004L86",
        asset_type="OBLIGATION",
        asset_name="OAT BANK01 Frozen",
        issuer_org_id=BANK01_ORG_ID,
        current_owner_id=THOMAS_USER_ID,
        nominal_value=Decimal("50000000"),
        current_value=Decimal("50000000"),
        currency="EUR",
        status="GELE",
        issuance_date=date(2025, 1, 15),
    )
    async_session.add(asset)
    await async_session.flush()

    payload = {
        "asset_id": "RWA-OBL-BANK01-2025-001",
        "to_owner": "sophie.lambert@amf.fr",
        "price": 24739375,
        "justification": "Tentative transfert actif gele test integration",
    }
    resp = await test_client.post(
        "/api/v1/assets/transfer",
        json=payload,
        headers={"Authorization": f"Bearer {token_thomas_martin}"},
    )
    assert resp.status_code == 409
    assert "REG01-INV-2026-001" in resp.json().get("message", "")

async def test_get_asset_returns_all_fields(
    test_client: AsyncClient, token_thomas_martin: str,
    async_session: AsyncSession, test_org, test_user_thomas,
):
    resp = await test_client.get(
        "/api/v1/assets/RWA-OBL-BANK01-2025-001",
        headers={"Authorization": f"Bearer {token_thomas_martin}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["asset_id"] == "RWA-OBL-BANK01-2025-001"
    assert "isin" in body
    assert "status" in body

async def test_get_asset_not_found_returns_404(
    test_client: AsyncClient, token_thomas_martin: str,
    async_session: AsyncSession, test_org, test_user_thomas,
):
    resp = await test_client.get(
        "/api/v1/assets/RWA-INEXISTANT-001",
        headers={"Authorization": f"Bearer {token_thomas_martin}"},
    )
    assert resp.status_code == 404
    assert "introuvable" in resp.json().get("message", "")

async def test_get_history_returns_3_ordered_provenance_records(
    test_client: AsyncClient, token_thomas_martin: str,
    async_session: AsyncSession, test_org, test_user_thomas,
):
    resp = await test_client.get(
        "/api/v1/assets/RWA-OBL-BANK01-2025-001/history",
        headers={"Authorization": f"Bearer {token_thomas_martin}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 3
    actions = [r["action"] for r in body]
    assert actions == ["TOKENISE", "TRANSFERE", "GELE"]

async def test_get_assets_filter_status_actif_excludes_frozen(
    test_client: AsyncClient, token_thomas_martin: str,
    async_session: AsyncSession, test_org, test_user_thomas,
):
    resp = await test_client.get(
        "/api/v1/assets?status=ACTIF",
        headers={"Authorization": f"Bearer {token_thomas_martin}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    frozen_ids = [a["asset_id"] for a in body if a.get("status") == "GELE"]
    assert "RWA-OBL-BANK01-2025-001" not in frozen_ids
