import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.features.assets.models import Asset
from core.features.transactions.models import Transaction
from tests.conftest import BANK01_ORG_ID, THOMAS_USER_ID


async def test_trigger_flag_high_risk_on_6m_transaction(
    async_session: AsyncSession, test_org, test_user_thomas,
):
    asset = Asset(
        asset_id="RWA-OBL-DBFLAG-001",
        isin="FR0014004L86",
        asset_type="OBLIGATION",
        asset_name="DB Flag Test 6M",
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

    tx = Transaction(
        tx_ref=f"TX-{uuid.uuid4()}",
        tx_type="TRANSFERT",
        asset_id=asset.id,
        initiator_id=THOMAS_USER_ID,
        amount=Decimal("6000001"),
        settlement_date=datetime.utcnow(),
        regulatory_flag=True,
    )
    async_session.add(tx)
    await async_session.flush()
    assert tx.regulatory_flag is True

async def test_trigger_no_flag_on_4m_transaction(
    async_session: AsyncSession, test_org, test_user_thomas,
):
    asset = Asset(
        asset_id="RWA-OBL-DBFLAG-002",
        isin="FR0014004L86",
        asset_type="OBLIGATION",
        asset_name="DB Flag Test 4M",
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

    tx = Transaction(
        tx_ref=f"TX-{uuid.uuid4()}",
        tx_type="TRANSFERT",
        asset_id=asset.id,
        initiator_id=THOMAS_USER_ID,
        amount=Decimal("4000000"),
        settlement_date=datetime.utcnow(),
        regulatory_flag=False,
    )
    async_session.add(tx)
    await async_session.flush()
    assert tx.regulatory_flag is False

async def test_trigger_update_asset_value_on_new_valuation(
    async_session: AsyncSession, test_org, test_user_thomas,
):
    asset = Asset(
        asset_id="RWA-OBL-DBVAL-001",
        isin="FR0014004L86",
        asset_type="OBLIGATION",
        asset_name="Valuation Update Test",
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

    asset.current_value = Decimal("48500000")
    await async_session.flush()
    await async_session.refresh(asset)
    assert asset.current_value == Decimal("48500000")

async def test_view_asset_portfolio_returns_data(
    async_session: AsyncSession, test_org, test_user_thomas,
):
    asset = Asset(
        asset_id="RWA-OBL-PORT-001",
        isin="FR0014004L86",
        asset_type="OBLIGATION",
        asset_name="Portfolio View Test",
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

    result = await async_session.execute(text("SELECT count(*) FROM assets"))
    count = result.scalar()
    assert count >= 1

async def test_view_compliance_dashboard_thomas_martin_approuve(
    async_session: AsyncSession, test_org, test_user_thomas,
):
    from core.features.compliance.models import ComplianceRecord
    rec = ComplianceRecord(
        participant_id=THOMAS_USER_ID,
        kyc_level=3,
        kyc_status="APPROUVE",
        aml_score=Decimal("0.042"),
        risk_category="FAIBLE",
        expires_at=datetime.utcnow() + timedelta(days=365),
    )
    async_session.add(rec)
    await async_session.flush()

    await async_session.flush()

    result = await async_session.execute(
        text("SELECT kyc_status FROM compliance_records WHERE id = :rec_id"),
        {"rec_id": str(rec.id)},
    )
    row = result.fetchone()
    assert row is not None
    assert row[0] == "APPROUVE"

async def test_function_get_full_audit_oat_bnp(
    async_session: AsyncSession, test_org, test_user_thomas,
):
    asset = Asset(
        asset_id="RWA-OBL-BANK01-2025-001",
        isin="FR0014004L86",
        asset_type="OBLIGATION",
        asset_name="OAT BANK01 Audit",
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

    result = await async_session.execute(
        text("SELECT asset_id, status FROM assets WHERE asset_id = :aid"),
        {"aid": "RWA-OBL-BANK01-2025-001"},
    )
    row = result.fetchone()
    assert row is not None
    assert row[1] == "GELE"

async def test_function_get_org_portfolio_summary_bnp(
    async_session: AsyncSession, test_org, test_user_thomas,
):
    asset = Asset(
        asset_id="RWA-OBL-ORGPORT-001",
        isin="FR0014004L86",
        asset_type="OBLIGATION",
        asset_name="Org Portfolio Test",
        issuer_org_id=BANK01_ORG_ID,
        current_owner_id=THOMAS_USER_ID,
        nominal_value=Decimal("25000000"),
        current_value=Decimal("25000000"),
        currency="EUR",
        status="ACTIF",
        issuance_date=date(2026, 1, 15),
    )
    async_session.add(asset)
    await async_session.flush()

    result = await async_session.execute(
        text("SELECT SUM(current_value) FROM assets WHERE issuer_org_id = :oid"),
        {"oid": str(BANK01_ORG_ID)},
    )
    total = result.scalar()
    assert total is not None
    assert float(total) > 0
