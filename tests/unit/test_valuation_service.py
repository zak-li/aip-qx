from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.features.assets.models import Asset
from core.features.assets.valuation_service import get_history, record_valuation
from core.features.auth.models import Organization, User


@pytest.fixture
async def seed_valuation_asset(async_session: AsyncSession) -> str:
    org_id = uuid4()
    org = Organization(
        id=org_id, legal_name="Valuation Org", msp_id=f"MSP-{uuid4()}",
        org_code="VAL", org_type="BANQUE", is_active=True
    )
    await async_session.merge(org)
    
    user_id = uuid4()
    user = User(
        id=user_id, email=f"val-{uuid4()}@val.com", role="EMETTEUR",
        keycloak_sub=f"kc-sub-val-{user_id}", org_id=org_id, is_active=True
    )
    await async_session.merge(user)

    a_id = uuid4()
    asset_id = f"RWA-VAL-{uuid4()}"
    asset = Asset(
        id=a_id,
        asset_id=asset_id,
        asset_type="OBLIGATION",
        asset_name="Obligation BANK01",
        issuer_org_id=org_id,
        current_owner_id=user_id,
        nominal_value=Decimal("100"),
        current_value=Decimal("100"),
        currency="EUR",
        status="ACTIF",
        issuance_date=date(2025, 1, 1),
    )
    await async_session.merge(asset)
    await async_session.flush()
    return asset_id

@pytest.mark.asyncio
async def test_record_valuation_inserts_row(async_session: AsyncSession, seed_valuation_asset: str) -> None:
    val = await record_valuation(
        async_session,
        asset_id=seed_valuation_asset,
        current_value=Decimal("24739375"),
        yield_to_maturity=Decimal("0.0375")
    )
    assert val.nav == Decimal("24739375")
    assert val.yield_to_maturity == Decimal("0.0375")

@pytest.mark.asyncio
async def test_record_valuation_triggers_asset_update(async_session: AsyncSession, seed_valuation_asset: str) -> None:
    await record_valuation(
        async_session,
        asset_id=seed_valuation_asset,
        current_value=Decimal("24739375"),
    )
    stmt = text("SELECT current_value FROM assets WHERE asset_id=:aid")
    result = await async_session.execute(stmt, {"aid": seed_valuation_asset})
    row = result.fetchone()
    assert row is not None
    assert row[0] == Decimal("24739375")

@pytest.mark.asyncio
async def test_get_history_returns_ordered_by_date(async_session: AsyncSession, seed_valuation_asset: str) -> None:
    from datetime import date, timedelta
    
    today = date.today()
    yesterday = today - timedelta(days=1)
    day_before = today - timedelta(days=2)
    
    await record_valuation(async_session, seed_valuation_asset, current_value=Decimal("101"), valuation_date=day_before)
    await record_valuation(async_session, seed_valuation_asset, current_value=Decimal("103"), valuation_date=today)
    await record_valuation(async_session, seed_valuation_asset, current_value=Decimal("102"), valuation_date=yesterday)
    
    history = await get_history(async_session, seed_valuation_asset)
    assert len(history) == 3
    assert history[0].nav == Decimal("103")
    assert history[1].nav == Decimal("102")
    assert history[2].nav == Decimal("101")
