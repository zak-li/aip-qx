import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from backend.features.compliance.kyc import KYCVerifier
from backend.features.compliance.aml import AMLScorer
from backend.features.compliance.rules_mica import MiCAChecker
from backend.features.compliance.sanctions import SanctionsScreener
from backend.config import settings
from backend.features.compliance.models import ComplianceRecord
from tests.conftest import THOMAS_USER_ID, JAMES_USER_ID

async def _seed_compliance(session: AsyncSession, user_id: uuid.UUID, level: int, status: str, expires_at: datetime, score: Decimal):
    rec = ComplianceRecord(
        participant_id=user_id,
        kyc_level=level,
        kyc_status=status,
        aml_score=score,
        risk_category="FAIBLE",
        expires_at=expires_at,
    )
    session.add(rec)
    await session.flush()
    return rec

async def test_kyc_thomas_martin_approved_level_3(
    async_session: AsyncSession, test_org, test_user_thomas,
):
    await _seed_compliance(
        async_session, THOMAS_USER_ID, 3, "APPROUVE",
        datetime(2027, 6, 15, tzinfo=timezone.utc), Decimal("0.042"),
    )
    verifier = KYCVerifier(settings, async_session)
    result = await verifier.verify(THOMAS_USER_ID)
    assert result.approved is True
    assert result.level == 3
    assert result.expires_at.year == 2027

async def test_kyc_james_wilson_expired_after_20260228(
    async_session: AsyncSession, test_org, test_user_thomas,
):
    james_id = JAMES_USER_ID
    from backend.features.auth.models import Organization, User
    from backend.core.security import hash_password
    natwest = Organization(
        id=uuid.UUID("00000000-0000-0000-0000-000000000003"),
        org_code="NW", legal_name="NatWest", org_type="BANQUE",
        msp_id="NatWestMarketsMSP", is_active=True,
    )
    async_session.add(natwest)
    await async_session.flush()
    james = User(
        id=james_id, org_id=natwest.id, email="james.wilson@natwest.com",
        hashed_password=hash_password("Passw0rd!"), role="TRADER", is_active=True,
    )
    async_session.add(james)
    await async_session.flush()

    await _seed_compliance(
        async_session, james_id, 3, "APPROUVE",
        datetime(2026, 2, 28, tzinfo=timezone.utc), Decimal("0.089"),
    )

    with patch("backend.features.compliance.kyc.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 3, 1, tzinfo=timezone.utc)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        verifier = KYCVerifier(settings, async_session)
        result = await verifier.verify(james_id)

    assert result.approved is False
    assert "2026-02-28" in result.reason

async def test_kyc_james_wilson_needs_renewal_flag(
    async_session: AsyncSession, test_org, test_user_thomas,
):
    james_id = JAMES_USER_ID
    from backend.features.auth.models import Organization, User
    try:
        natwest = Organization(
            id=uuid.UUID("00000000-0000-0000-0000-000000000003"),
            org_code="NW2", legal_name="NatWest2", org_type="BANQUE",
            msp_id="NatWestMSP2", is_active=True,
        )
        async_session.add(natwest)
        await async_session.flush()
    except Exception:
        pass

    try:
        james = User(
            id=james_id, org_id=uuid.UUID("00000000-0000-0000-0000-000000000003"),
            email="james2@natwest.com", hashed_password="$2b$12$fakehash",
            role="TRADER", is_active=True,
        )
        async_session.add(james)
        await async_session.flush()
    except Exception:
        pass

    await _seed_compliance(
        async_session, james_id, 3, "APPROUVE",
        datetime(2026, 2, 28, tzinfo=timezone.utc), Decimal("0.089"),
    )

    with patch("backend.features.compliance.kyc.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 1, 30, tzinfo=timezone.utc)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        verifier = KYCVerifier(settings, async_session)
        result = await verifier.verify(james_id)

    assert result.needs_renewal is True

async def test_aml_score_thomas_martin_equals_0042(
    async_session: AsyncSession, test_org, test_user_thomas,
):
    scorer = AMLScorer(settings, async_session)
    result = await scorer.score(THOMAS_USER_ID, 1000000.0, uuid.uuid4())
    assert abs(result.score - 0.042) < 0.005
    assert result.risk_category == "FAIBLE"
    assert result.blocked is False
    assert result.sar_required is False

async def test_aml_score_james_wilson_equals_0089(
    async_session: AsyncSession, test_org, test_user_thomas,
):
    scorer = AMLScorer(settings, async_session)
    result = await scorer.score(JAMES_USER_ID, 1000000.0, uuid.uuid4())
    assert abs(result.score - 0.089) < 0.01
    assert result.blocked is False

async def test_aml_large_amount_bonus_applied(
    async_session: AsyncSession, test_org, test_user_thomas,
):
    scorer = AMLScorer(settings, async_session)
    result_small = await scorer.score(THOMAS_USER_ID, 1000.0, uuid.uuid4())
    result_large = await scorer.score(THOMAS_USER_ID, 30000000.0, uuid.uuid4())
    assert result_large.score > result_small.score

async def test_aml_blocked_when_score_above_060(
    async_session: AsyncSession, test_org, test_user_thomas,
):
    scorer = AMLScorer(settings, async_session)
    with patch.object(scorer, "_load_indicators") as mock_ind:
        from backend.features.compliance.aml import AMLIndicators
        mock_ind.return_value = AMLIndicators(0.7, 0.7, 0.7)
        result = await scorer.score(THOMAS_USER_ID, 1000.0, uuid.uuid4())
    assert result.blocked is True
    assert result.blocked_reason is not None

async def test_aml_sar_required_when_score_above_075(
    async_session: AsyncSession, test_org, test_user_thomas,
):
    scorer = AMLScorer(settings, async_session)
    with patch.object(scorer, "_load_indicators") as mock_ind:
        from backend.features.compliance.aml import AMLIndicators
        mock_ind.return_value = AMLIndicators(0.9, 0.9, 0.9)
        result = await scorer.score(THOMAS_USER_ID, 1000.0, uuid.uuid4())
    assert result.sar_required is True

async def test_mica_art68_triggered_above_1000_eur(
    async_session: AsyncSession, test_org, test_user_thomas,
):
    checker = MiCAChecker(settings, async_session)
    with patch("backend.features.compliance.rules_mica.get_redis") as mock_redis:
        mock_gen = AsyncMock()
        mock_conn = AsyncMock()
        mock_gen.__anext__ = AsyncMock(return_value=mock_conn)
        mock_gen.aclose = AsyncMock()
        mock_redis.return_value = mock_gen
        result = await checker.check(1001.0, THOMAS_USER_ID, "RWA-OBL-BNP-2025-001", "OBLIGATION")
    assert result.identification_required is True

async def test_mica_art68_not_triggered_below_1000_eur(
    async_session: AsyncSession, test_org, test_user_thomas,
):
    checker = MiCAChecker(settings, async_session)
    with patch("backend.features.compliance.rules_mica.get_redis") as mock_redis:
        mock_gen = AsyncMock()
        mock_conn = AsyncMock()
        mock_gen.__anext__ = AsyncMock(return_value=mock_conn)
        mock_gen.aclose = AsyncMock()
        mock_redis.return_value = mock_gen
        result = await checker.check(999.0, THOMAS_USER_ID, "RWA-OBL-BNP-2025-001", "OBLIGATION")
    assert result.identification_required is False
    assert result.compliant is True

async def test_mica_art76_missing_isin_produces_non_blocking_violation(
    async_session: AsyncSession, test_org, test_user_thomas,
):
    checker = MiCAChecker(settings, async_session)
    with patch("backend.features.compliance.rules_mica.get_redis") as mock_redis:
        mock_gen = AsyncMock()
        mock_conn = AsyncMock()
        mock_gen.__anext__ = AsyncMock(return_value=mock_conn)
        mock_gen.aclose = AsyncMock()
        mock_redis.return_value = mock_gen
        result = await checker.check(500.0, THOMAS_USER_ID, "INVALID-NO-RWA", "OBLIGATION")
    has_76 = any(v.article == "ART76" for v in result.violations)
    assert has_76 is True
    assert all(v.blocking is False for v in result.violations)

async def test_sanctions_thomas_martin_no_hit():
    screener = SanctionsScreener(settings)
    result = await screener.screen(THOMAS_USER_ID, "Thomas Martin")
    assert result.hit is False
    assert len(result.screened_lists) > 0

async def test_sanctions_james_wilson_no_hit():
    screener = SanctionsScreener(settings)
    result = await screener.screen(JAMES_USER_ID, "James Wilson")
    assert result.hit is False

async def test_sanctions_fuzzy_match_above_85_detected():
    screener = SanctionsScreener(settings)
    result = await screener.screen(uuid.uuid4(), "Jamez Wilzon")
    assert result.hit is True
    assert any(m.match_score > 80 for m in result.matches)
