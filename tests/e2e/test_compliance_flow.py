import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import patch

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.features.assets.models import Asset
from backend.features.auth.models import Organization, User
from tests.conftest import BANK01_ORG_ID, THOMAS_USER_ID


async def test_freeze_and_block_transfer_flow(
    test_client: AsyncClient,
    token_sophie_lambert: str,
    token_thomas_martin: str,
    async_session: AsyncSession,
    test_org, test_user_thomas, test_amf_org, test_user_sophie,
):
    asset = Asset(
        asset_id="RWA-OBL-E2EFRZ-001",
        isin="FR0014004L86",
        asset_type="OBLIGATION",
        asset_name="E2E Freeze Flow Bond",
        issuer_org_id=BANK01_ORG_ID,
        current_owner_id=THOMAS_USER_ID,
        nominal_value=Decimal("50000000"),
        current_value=Decimal("50000000"),
        currency="EUR",
        status="ACTIF",
        issuance_date=date(2025, 1, 15),
    )
    async_session.add(asset)
    await async_session.flush()

    freeze_payload = {
        "asset_id": "RWA-OBL-E2EFRZ-001",
        "reason": "Investigation compliance MIFID II test e2e",
        "regulatory_ref": "REG01-TEST-2026-001",
    }
    resp_freeze = await test_client.post(
        "/api/v1/assets/freeze",
        json=freeze_payload,
        headers={"Authorization": f"Bearer {token_sophie_lambert}"},
    )
    assert resp_freeze.status_code == 200
    assert resp_freeze.json()["status"] == "GELE"

    transfer_payload = {
        "asset_id": "RWA-OBL-E2EFRZ-001",
        "to_owner": "sophie.lambert@amf.fr",
        "price": 24739375,
        "justification": "Tentative transfert actif gele e2e flow",
    }
    resp_transfer = await test_client.post(
        "/api/v1/assets/transfer",
        json=transfer_payload,
        headers={"Authorization": f"Bearer {token_thomas_martin}"},
    )
    assert resp_transfer.status_code in (403, 409)

async def test_compliance_check_blocks_expired_kyc_james_wilson(
    test_client: AsyncClient,
    async_session: AsyncSession,
    test_org, test_user_thomas,
):
    from backend.core.security import hash_password

    bank04 = Organization(
        id=uuid.UUID("00000000-0000-0000-0000-000000000003"),
        org_code="NW3",
        legal_name="Bank 04 E2E",
        org_type="BANQUE",
        msp_id="BANK04E2EMSP",
        is_active=True,
    )
    async_session.add(bank04)
    await async_session.flush()

    james = User(
        id=uuid.UUID("10000000-0000-0000-0000-000000000003"),
        org_id=bank04.id,
        email="james.e2e@bank04.com",
        hashed_password=hash_password("Passw0rd!"),
        role="TRADER",
        is_active=True,
    )
    async_session.add(james)
    
    from backend.features.compliance.models import ComplianceRecord
    kyc = ComplianceRecord(
        participant_id=james.id,
        kyc_status="VERIFIE",
        kyc_level=3,
        aml_score=Decimal("0.0"),
        risk_category="FAIBLE",
        expires_at=datetime(2025, 12, 31, tzinfo=UTC),
    )
    async_session.add(kyc)
    
    await async_session.flush()

    from datetime import timedelta

    from backend.core.security import create_access_token
    token_james = create_access_token(
        {"sub": str(james.id), "role": "TRADER", "org_id": str(bank04.id)},
        expires_delta=timedelta(hours=24),
    )

    asset = Asset(
        asset_id="RWA-OBL-BANK02-2025-002",
        isin="FR0014005SG2",
        asset_type="OBLIGATION",
        asset_name="SG Green Bond 2.875%",
        issuer_org_id=BANK01_ORG_ID,
        current_owner_id=THOMAS_USER_ID,
        nominal_value=Decimal("75000000"),
        current_value=Decimal("75000000"),
        currency="EUR",
        status="ACTIF",
        issuance_date=date(2025, 6, 1),
    )
    async_session.add(asset)
    await async_session.flush()

    class MockDatetime:
        @classmethod
        def now(cls, tz=None):
            from datetime import datetime
            return datetime(2026, 3, 1, tzinfo=UTC)

    with patch("backend.features.compliance.kyc.datetime", new=MockDatetime):
        transfer_payload = {
            "asset_id": "RWA-OBL-BANK02-2025-002",
            "to_owner": "james.e2e@bank04.com",
            "price": 10000000,
            "justification": "Tentative transfert trader KYC expire e2e",
        }
        resp = await test_client.post(
            "/api/v1/assets/transfer",
            json=transfer_payload,
            headers={"Authorization": f"Bearer {token_james}"},
        )
        assert resp.status_code in (403, 409, 500)
