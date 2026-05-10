import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.security import hash_password
from backend.exceptions import AssetFrozenError
from backend.features.assets.models import Asset
from backend.features.auth.models import User
from backend.features.assets.schemas import FreezeRequest, TransferRequest
from tests.conftest import BNP_ORG_ID, AMF_ORG_ID, THOMAS_USER_ID


@pytest.fixture
async def seeded_asset(async_session: AsyncSession, test_org, test_user_thomas) -> Asset:
    asset = Asset(
        asset_id="RWA-OBL-SAGA-2026-001",
        isin="FR0014004L99",
        asset_type="OBLIGATION",
        asset_name="OAT SAGA Test",
        issuer_org_id=BNP_ORG_ID,
        current_owner_id=THOMAS_USER_ID,
        nominal_value=Decimal("1000000"),
        current_value=Decimal("1000000"),
        currency="EUR",
        status="ACTIF",
        issuance_date=date(2026, 1, 15),
    )
    async_session.add(asset)
    await async_session.flush()
    return asset


@pytest.fixture
async def seeded_frozen_asset(async_session: AsyncSession, test_org, test_user_thomas) -> Asset:
    asset = Asset(
        asset_id="RWA-OBL-SAGA-2026-002",
        isin="FR0014004L88",
        asset_type="OBLIGATION",
        asset_name="OAT SAGA Frozen",
        issuer_org_id=BNP_ORG_ID,
        current_owner_id=THOMAS_USER_ID,
        nominal_value=Decimal("2000000"),
        current_value=Decimal("2000000"),
        currency="EUR",
        status="GELE",
        issuance_date=date(2026, 1, 15),
    )
    async_session.add(asset)
    await async_session.flush()
    return asset


async def test_transfer_saga_compensation_on_db_failure(
    async_session: AsyncSession, test_org, test_user_thomas, test_amf_org, mock_fabric_client, seeded_asset
):
    from backend.features.assets.service import transfer

    recipient = User(
        id=uuid.UUID("30000000-0000-0000-0000-000000000001"),
        org_id=AMF_ORG_ID,
        email="recipient@amf.fr",
        hashed_password=hash_password("Passw0rd!"),
        role="TRADER",
        is_active=True,
    )
    async_session.add(recipient)
    await async_session.flush()

    transfer_result = {"txID": "SAGA_TX_001", "blockNumber": 10, "status": "TRANSFERE"}
    mock_fabric_client.submit_transaction.return_value = transfer_result

    with patch("backend.features.assets.service.full_check", return_value=(False, "", "")):
        with patch.object(async_session, "commit", side_effect=[Exception("Simulated DB failure")]):
            with pytest.raises(Exception, match="Simulated DB failure"):
                request = TransferRequest(
                    asset_id="RWA-OBL-SAGA-2026-001",
                    to_owner="recipient@amf.fr",
                    price=Decimal("950000"),
                    justification="Test SAGA transfer compensation",
                )
                await transfer(request, "Admin@bank01", async_session, current_user=test_user_thomas)

    submit_calls = mock_fabric_client.submit_transaction.call_args_list
    call_functions = [c[0][0] for c in submit_calls]
    assert "TransferAsset" in call_functions
    assert "TransferAsset" in call_functions[1:]


async def test_freeze_saga_compensation_on_db_failure(
    async_session: AsyncSession, test_org, test_user_thomas, test_amf_org, mock_fabric_client, seeded_asset
):
    from backend.features.assets.service import freeze

    freeze_result = {"txID": "SAGA_FREEZE_001", "blockNumber": 11}
    mock_fabric_client.submit_transaction.return_value = freeze_result

    with patch.object(async_session, "commit", side_effect=[Exception("DB failure on freeze")]):
        with pytest.raises(Exception, match="DB failure on freeze"):
            request = FreezeRequest(
                asset_id="RWA-OBL-SAGA-2026-001",
                reason="Test regulatory freeze",
                regulatory_ref="AMF-INV-2026-001",
            )
            await freeze(request, "Admin@amf-regulateur", async_session)

    submit_calls = mock_fabric_client.submit_transaction.call_args_list
    call_functions = [c[0][0] for c in submit_calls]
    assert "FreezeAsset" in call_functions
    assert "UnfreezeAsset" in call_functions


async def test_fabric_endorsement_error_propagates(
    async_session: AsyncSession, test_org, test_user_thomas, mock_fabric_client, seeded_asset
):
    from backend.features.assets.service import freeze
    from backend.fabric_client.network import FabricEndorsementError

    mock_fabric_client.submit_transaction.side_effect = FabricEndorsementError("Endorsement failed")

    with pytest.raises(FabricEndorsementError):
        request = FreezeRequest(
            asset_id="RWA-OBL-SAGA-2026-001",
            reason="Test error propagation",
            regulatory_ref="AMF-INV-2026-002",
        )
        await freeze(request, "Admin@amf-regulateur", async_session)


async def test_fabric_frozen_error_propagates_on_transfer(
    async_session: AsyncSession, test_org, test_user_thomas, test_amf_org, mock_fabric_client
):
    from backend.features.assets.service import transfer

    frozen_asset = Asset(
        asset_id="RWA-OBL-BNP-2025-001",
        isin="FR0014004L86",
        asset_type="OBLIGATION",
        asset_name="OAT BNP 3.75% 2030",
        issuer_org_id=BNP_ORG_ID,
        current_owner_id=THOMAS_USER_ID,
        nominal_value=Decimal("50000000"),
        current_value=Decimal("50000000"),
        currency="EUR",
        status="GELE",
        issuance_date=date(2025, 1, 15),
    )
    async_session.add(frozen_asset)
    await async_session.flush()

    recipient = User(
        id=uuid.UUID("30000000-0000-0000-0000-000000000002"),
        org_id=AMF_ORG_ID,
        email="buyer.frozen@amf.fr",
        hashed_password=hash_password("Passw0rd!"),
        role="TRADER",
        is_active=True,
    )
    async_session.add(recipient)
    await async_session.flush()

    with patch("backend.features.assets.service.full_check", return_value=(False, "", "")):
        with pytest.raises(AssetFrozenError):
            request = TransferRequest(
                asset_id="RWA-OBL-BNP-2025-001",
                to_owner="buyer.frozen@amf.fr",
                price=Decimal("49000000"),
                justification="Transfer frozen asset",
            )
            await transfer(request, "Admin@bank01", async_session, current_user=test_user_thomas)
