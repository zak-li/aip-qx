from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core.features.auth.models import Organization, User
from core.features.compliance.models import ComplianceRecord
from tests.conftest import THOMAS_USER_ID


@pytest.fixture
async def user_with_expiring_kyc(async_session: AsyncSession, test_org: Organization, test_user_thomas: User):
    rec = ComplianceRecord(
        participant_id=THOMAS_USER_ID,
        kyc_status="VERIFIE",
        kyc_level=3,
        aml_score=Decimal("0.042"),
        risk_category="FAIBLE",
        expires_at=datetime.now(UTC) + timedelta(days=15),
    )
    async_session.add(rec)
    await async_session.flush()
    return rec


async def test_check_kyc_expiry_detects_expiring_records(
    async_session: AsyncSession, test_org, user_with_expiring_kyc
):
    from core.features.compliance.tasks import _do_kyc_expiry

    with patch("core.features.compliance.tasks.AsyncSessionLocal") as mock_session_local:
        mock_ctx = AsyncMock()
        mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_rows = [(THOMAS_USER_ID, "thomas.martin@bank01.fr", datetime.now(UTC) + timedelta(days=15))]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = mock_rows

        now_result = MagicMock()
        now_result.scalar.return_value = datetime.now(UTC)

        mock_ctx.execute = AsyncMock(side_effect=[mock_result, now_result, MagicMock()])
        mock_ctx.commit = AsyncMock()

        with patch("core.features.compliance.tasks.log_task_audit", AsyncMock()):
            result = await _do_kyc_expiry()

    assert result["checked"] == 1
    assert result["warnings"] == 1


async def test_generate_sar_creates_sar_report(
    async_session: AsyncSession, test_org, test_user_thomas
):
    from core.features.compliance.tasks import _do_generate_sar

    with patch("core.features.compliance.tasks.AsyncSessionLocal") as mock_session_local:
        mock_ctx = AsyncMock()
        mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)

        captured_sar_ref = []

        async def fake_sar_generate(participant_id, tx_id, reason_code, amount, regulatory_ref):
            ref = "TMA-2026-001-UNKNOWN"
            captured_sar_ref.append(ref)
            return ref

        with patch("core.features.compliance.tasks.SARReporter") as mock_reporter_class:
            mock_reporter = AsyncMock()
            mock_reporter.generate.side_effect = fake_sar_generate
            mock_reporter_class.return_value = mock_reporter

            with patch("core.features.compliance.tasks.log_task_audit", AsyncMock()):
                ref = await _do_generate_sar(
                    participant_id=str(THOMAS_USER_ID),
                    tx_id=None,
                    reason_code="AML_CRITICAL_THRESHOLD",
                    amount=5000000.0,
                    regulatory_ref=None,
                )

    assert ref.startswith("TMA-")


async def test_fraud_graph_scan_returns_summary():
    from core.features.compliance.tasks import _do_fraud_graph_scan

    mock_results = {
        "circular_flow": [{"actor_dn": "actor1", "cycle_length": 3, "total_volume": 1000.0, "pattern": "CIRCULAR_FLOW"}],
        "smurfing": [],
        "layering": [],
        "transfer_concentration": [],
    }

    with patch("core.features.compliance.tasks.get_neo4j_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.close = AsyncMock()
        mock_client.run_fraud_scan = AsyncMock(return_value=mock_results)
        mock_get_client.return_value = mock_client

        with patch("core.features.compliance.tasks.log_task_audit", AsyncMock()):
            result = await _do_fraud_graph_scan()

    assert result["total_anomalies"] == 1
    assert result["circular_flow"] == 1
    assert result["smurfing"] == 0


async def test_run_periodic_aml_screening_uses_real_scorer():
    from core.features.compliance.tasks import _do_aml_screening

    with patch("core.features.compliance.tasks.AsyncSessionLocal") as mock_session_local:
        mock_ctx = AsyncMock()
        mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_users_result = MagicMock()
        mock_users_result.scalars.return_value.all.return_value = [str(THOMAS_USER_ID)]
        mock_ctx.execute = AsyncMock(return_value=mock_users_result)
        mock_ctx.commit = AsyncMock()

        with patch("core.features.compliance.tasks.AMLScorer") as mock_scorer_class:
            from core.features.compliance.aml import AMLResult as AMLResultInternal
            mock_scorer = AsyncMock()
            mock_scorer.score = AsyncMock(return_value=AMLResultInternal(
                score=0.42,
                risk_category="MOYEN",
                blocked=False,
                blocked_reason=None,
                indicators=[],
                sar_required=False,
            ))
            mock_scorer_class.return_value = mock_scorer

            with patch("core.features.compliance.tasks.log_task_audit", AsyncMock()):
                result = await _do_aml_screening()

    assert "screened" in result
    assert result["screened"] == 1
