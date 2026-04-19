
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def test_complete_tokenization_and_read_flow(
    test_client: AsyncClient, token_thomas_martin: str,
    async_session: AsyncSession, test_org, test_user_thomas,
):
    payload = {
        "asset_id": "RWA-DRV-TEST-2026-001",
        "isin": "FR0000TEST01",
        "asset_type": "DERIVE",
        "asset_name": "IRS EUR 5Y E2E Test",
        "issuer_lei": "R0MUWSFPU8MPRO8K5P83",
        "nominal_value": 5000000,
        "currency": "EUR",
        "issuance_date": "2026-01-15",
        "justification": "Tokenisation E2E test flow complet derive",
    }

    resp_create = await test_client.post(
        "/api/v1/assets/tokenize",
        json=payload,
        headers={"Authorization": f"Bearer {token_thomas_martin}"},
    )
    assert resp_create.status_code == 201
    body_create = resp_create.json()
    assert body_create["asset_id"] == "RWA-DRV-TEST-2026-001"
    assert body_create["status"] == "ACTIF"
    assert body_create["fabric_tx_id"] is not None
    assert body_create["fabric_tx_id"] != ""

    resp_read = await test_client.get(
        "/api/v1/assets/RWA-DRV-TEST-2026-001",
        headers={"Authorization": f"Bearer {token_thomas_martin}"},
    )
    assert resp_read.status_code == 200

    result = await async_session.execute(
        text("SELECT asset_id, fabric_tx_id FROM assets WHERE asset_id = :aid"),
        {"aid": "RWA-DRV-TEST-2026-001"},
    )
    row = result.fetchone()
    assert row is not None
    assert row[1] is not None
    assert row[1] != ""
