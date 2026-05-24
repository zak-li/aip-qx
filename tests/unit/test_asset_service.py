import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import AssetFrozenError
from core.features.assets.models import Asset
from core.features.assets.schemas import FreezeRequest, TokenizeRequest, TransferRequest
from core.features.assets.service import freeze, tokenize, transfer
from core.features.auth.models import Organization, User
from tests.conftest import BANK01_ORG_ID, THOMAS_USER_ID


async def test_tokenize_creates_asset_and_calls_fabric(
    async_session: AsyncSession, test_org: Organization, test_user_thomas: User, mock_fabric_client: AsyncMock
):
    request = TokenizeRequest(
        asset_id="RWA-OBL-TEST-2026-001",
        isin="FR0014004L86",
        asset_type="OBLIGATION",
        asset_name="Test Bond 2026",
        issuer_lei="R0MUWSFPU8MPRO8K5P83",
        nominal_value=Decimal("50000000"),
        currency="EUR",
        issuance_date=date(2026, 1, 15),
        justification="Tokenisation test unitaire bond primaire",
    )

    with patch("core.features.assets.service.get_fabric", return_value=mock_fabric_client):
        with patch("core.features.assets.service.get_redis", side_effect=Exception("skip redis")):
            result = await tokenize(request, "admin@bank01", async_session)

    assert result.asset_id == "RWA-OBL-TEST-2026-001"
    assert result.fabric_tx_id == "abc123def456"
    assert result.status == "ACTIF"
    mock_fabric_client.submit_transaction.assert_called_once()
    call_args = mock_fabric_client.submit_transaction.call_args
    assert call_args[0][0] == "TokenizeAsset"

async def test_tokenize_raises_if_asset_already_exists(
    async_session: AsyncSession, test_org: Organization, test_user_thomas: User, mock_fabric_client: AsyncMock
):
    from core.exceptions import AssetAlreadyExistsError
    mock_fabric_client.submit_transaction.side_effect = AssetAlreadyExistsError("RWA-OBL-TEST-2026-002")

    request = TokenizeRequest(
        asset_id="RWA-OBL-TEST-2026-002",
        isin="FR0014004L86",
        asset_type="OBLIGATION",
        asset_name="Test Bond Duplicate",
        issuer_lei="R0MUWSFPU8MPRO8K5P83",
        nominal_value=Decimal("10000000"),
        currency="EUR",
        issuance_date=date(2026, 1, 15),
        justification="Tentative duplication test unitaire",
    )

    with patch("core.features.assets.service.get_fabric", return_value=mock_fabric_client):
        with pytest.raises(AssetAlreadyExistsError) as exc_info:
            await tokenize(request, "admin@bank01", async_session)

    assert "RWA-OBL-TEST-2026-002" in str(exc_info.value)

async def test_transfer_updates_owner_to_pierre_moreau(
    async_session: AsyncSession, test_org: Organization, test_user_thomas: User, mock_fabric_client: AsyncMock
):
    pierre = User(
        id=uuid.UUID("20000000-0000-0000-0000-000000000001"),
        org_id=BANK01_ORG_ID,
        email="pierre.moreau@cust01.fr",
        keycloak_sub="kc-sub-pierre-moreau-1",
        first_name="Pierre",
        last_name="Moreau",
        role="TRADER",
        msp_id="INV01ManagersMSP",
        is_active=True,
    )
    async_session.add(pierre)
    await async_session.flush()

    asset = Asset(
        asset_id="RWA-OBL-XFER-2026-001",
        isin="FR0014004L86",
        asset_type="OBLIGATION",
        asset_name="Xfer Test Bond",
        issuer_org_id=BANK01_ORG_ID,
        current_owner_id=THOMAS_USER_ID,
        nominal_value=Decimal("50000000"),
        current_value=Decimal("50000000"),
        currency="EUR",
        status="ACTIF",
        issuance_date=date(2026, 1, 15),
    )
    async_session.add(asset)
    await async_session.flush()

    mock_fabric_client.submit_transaction.side_effect = None
    mock_fabric_client.submit_transaction.return_value = {"txID": "XFER_TX_001", "blockNumber": 5, "status": "ACTIF"}

    request = TransferRequest(
        asset_id="RWA-OBL-XFER-2026-001",
        to_owner="pierre.moreau@cust01.fr",
        price=Decimal("24739375"),
        justification="Cession bloc Inv01 portefeuille ESG test",
    )

    with patch("core.features.assets.service.get_fabric", return_value=mock_fabric_client):
        with patch("core.features.assets.service.full_check", return_value=(False, None, None)):
            result = await transfer(request, "admin@bank01", async_session)

    assert result.current_value == Decimal("24739375")
    assert result.fabric_tx_id == "XFER_TX_001"

async def test_transfer_blocked_on_frozen_asset_returns_frozen_error(
    async_session: AsyncSession, test_org: Organization, test_user_thomas: User, mock_fabric_client: AsyncMock
):
    pierre = User(
        id=uuid.UUID("20000000-0000-0000-0000-000000000002"),
        org_id=BANK01_ORG_ID,
        email="pierre.moreau2@cust01.fr",
        keycloak_sub="kc-sub-pierre-moreau-2",
        role="TRADER",
        msp_id="INV01ManagersMSP",
        is_active=True,
    )
    async_session.add(pierre)
    await async_session.flush()

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

    mock_fabric_client.submit_transaction.side_effect = AssetFrozenError("RWA-OBL-BANK01-2025-001", "REG01-INV-2026-001")

    request = TransferRequest(
        asset_id="RWA-OBL-BANK01-2025-001",
        to_owner="pierre.moreau2@cust01.fr",
        price=Decimal("24739375"),
        justification="Tentative transfert actif gele test",
    )

    with patch("core.features.assets.service.get_fabric", return_value=mock_fabric_client):
        with patch("core.features.assets.service.full_check", return_value=(False, None, None)):
            with pytest.raises(AssetFrozenError) as exc_info:
                await transfer(request, "admin@bank01", async_session)

    assert "REG01-INV-2026-001" in str(exc_info.value)

async def test_freeze_sets_status_gele_in_fabric_and_postgres(
    async_session: AsyncSession, test_org: Organization, test_user_thomas: User, mock_fabric_client: AsyncMock
):
    asset = Asset(
        asset_id="RWA-OBL-FREEZE-2026-001",
        isin="FR0014004L86",
        asset_type="OBLIGATION",
        asset_name="Freeze Test Bond",
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

    mock_fabric_client.submit_transaction.side_effect = None
    mock_fabric_client.submit_transaction.return_value = {
        "txID": "FREEZE_TX_001", "blockNumber": 3, "status": "GELE"
    }

    request = FreezeRequest(
        asset_id="RWA-OBL-FREEZE-2026-001",
        reason="Investigation test unitaire MIFID II art.69",
        regulatory_ref="REG01-INV-2026-001",
    )

    with patch("core.features.assets.service.get_fabric", return_value=mock_fabric_client):
        result = await freeze(request, "admin@reg01-regulateur", async_session)

    assert result.status == "GELE"
    mock_fabric_client.submit_transaction.assert_called_once()

async def test_get_provenance_returns_3_records_ordered_chronologically(
    sample_provenance,
):
    assert len(sample_provenance) == 3
    assert sample_provenance[0].action == "TOKENISE"
    assert sample_provenance[1].action == "TRANSFERE"
    assert sample_provenance[2].action == "GELE"
    assert sample_provenance[0].timestamp < sample_provenance[1].timestamp
    assert sample_provenance[1].timestamp < sample_provenance[2].timestamp
