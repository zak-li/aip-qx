import json
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from core.core.redis_client import get_redis
from core.features.auth.models import Organization, User
from core.features.compliance.models import SARReport as SARReportORM

logger = logging.getLogger(__name__)

SARStatus = Literal["OUVERT", "SOUMIS", "CLOS"]

@dataclass
class SARReport:
    reference: str
    participant_id: uuid.UUID
    tx_id: uuid.UUID | None
    reason_code: str
    amount: float
    regulatory_ref: str | None
    status: SARStatus

class SARReporter:
    def __init__(self, settings: Settings, db: AsyncSession) -> None:
        self.settings = settings
        self.db = db

    async def _resolve_compliance_officer(self, participant_id: uuid.UUID) -> uuid.UUID:
        """Return the first active COMPLIANCE_OFFICER; fall back to participant if none exists."""
        stmt = (
            select(User.id)
            .where(User.role == "COMPLIANCE_OFFICER", User.is_active.is_(True))
            .limit(1)
        )
        result = await self.db.execute(stmt)
        officer_id = result.scalar_one_or_none()
        return officer_id if officer_id is not None else participant_id

    async def _resolve_org_code(self, participant_id: uuid.UUID) -> str:
        stmt = (
            select(Organization.org_code)
            .join(User, User.org_id == Organization.id)
            .where(User.id == participant_id)
            .limit(1)
        )
        result = await self.db.execute(stmt)
        code = result.scalar_one_or_none()
        return (code or "UNK")[:20]

    async def generate(self, participant_id: uuid.UUID, tx_id: uuid.UUID | None, reason_code: str, amount: float, regulatory_ref: str | None = None) -> str:
        year = datetime.now(UTC).year
        org_code = await self._resolve_org_code(participant_id)

        # Compose reference: TMA-YYYY-<6-hex>-<NNNN>-<ORG>
        # The 6-hex random suffix guarantees uniqueness even if Redis is unavailable
        # (the previous fallback would have collided on `1`). The Redis counter
        # gives a monotonically increasing sequence per year for human readability.
        try:
            redis_gen = get_redis()
            redis_conn = await redis_gen.__anext__()
            nnn_int = await redis_conn.incr(f"sar:counter:{year}")
            await redis_gen.aclose()
        except Exception as exc:
            logger.warning(f"Redis INCR indisponible pour SAR counter: {exc}")
            nnn_int = 0  # zero indicates no sequence available; uniqueness is on the random tail

        rand_tail = secrets.token_hex(3)
        ref = f"TMA-{year}-{rand_tail}-{nnn_int:04d}-{org_code}"

        reporting_officer = await self._resolve_compliance_officer(participant_id)

        report = SARReportORM(
            sar_ref=ref,
            reported_user_id=participant_id,
            reporting_officer=reporting_officer,
            transaction_id=tx_id,
            reason_code=reason_code,
            reason_description=reason_code,
            amount_involved=amount,
            submitted_to="TRACFIN",
            status="DRAFT",
        )
        self.db.add(report)
        await self.db.commit()

        try:
            redis_gen = get_redis()
            redis_conn = await redis_gen.__anext__()
            payload = {
                "reference": ref,
                "amount": amount,
                "status": "OUVERT",
                "participant_id": str(participant_id),
                "reason_code": reason_code,
                "timestamp": datetime.now(UTC).isoformat(),
            }
            await redis_conn.publish("compliance:sar", json.dumps(payload, default=str))
            await redis_gen.aclose()
        except Exception as exc:
            logger.warning(f"Publication Redis SAR échouée: {exc}")

        return ref

    async def get_active(self) -> list[SARReport]:
        stmt = select(SARReportORM).where(SARReportORM.status == "DRAFT")
        result = await self.db.execute(stmt)
        records = result.scalars().all()
        return [
            SARReport(
                reference=r.sar_ref,
                participant_id=r.reported_user_id,
                tx_id=r.transaction_id,
                reason_code=r.reason_code,
                amount=float(r.amount_involved or 0),
                regulatory_ref=r.acknowledgement_ref,
                status=r.status,
            )
            for r in records
        ]

    async def close(self, reference: str, closed_by_id: uuid.UUID) -> SARReport:
        stmt = select(SARReportORM).where(SARReportORM.sar_ref == reference)
        result = await self.db.execute(stmt)
        report = result.scalar_one()

        report.status = "SOUMIS"
        report.submission_date = datetime.now(UTC)
        await self.db.commit()
        await self.db.refresh(report)

        return SARReport(
            reference=report.sar_ref,
            participant_id=report.reported_user_id,
            tx_id=report.transaction_id,
            reason_code=report.reason_code,
            amount=float(report.amount_involved or 0),
            regulatory_ref=report.acknowledgement_ref,
            status=report.status,
        )
