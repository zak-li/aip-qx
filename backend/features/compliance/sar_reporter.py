import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import Settings
from backend.core.redis_client import get_redis
from backend.features.compliance.models import SARReport as SARReportORM

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

    async def generate(self, participant_id: uuid.UUID, tx_id: uuid.UUID | None, reason_code: str, amount: float, regulatory_ref: str | None = None) -> str:
        year = datetime.now(timezone.utc).year

        try:
            redis_gen = get_redis()
            redis_conn = await redis_gen.__anext__()
            nnn_int = await redis_conn.incr(f"sar:counter:{year}")
            await redis_gen.aclose()
        except Exception as exc:
            logger.warning(f"Redis INCR indisponible pour SAR counter: {exc}")
            nnn_int = 1

        org_code = "UNKNOWN"
        ref = f"TMA-{year}-{nnn_int:03d}-{org_code}"

        report = SARReportORM(
            sar_ref=ref,
            reported_user_id=participant_id,
            reporting_officer=participant_id,
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
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await redis_conn.publish("compliance:sar", json.dumps(payload, default=str))
            await redis_gen.aclose()
        except Exception as exc:
            logger.warning(f"Publication Redis SAR échouée: {exc}")

        return ref

    async def get_active(self) -> list[SARReport]:
        from sqlalchemy import select
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
        from sqlalchemy import select
        stmt = select(SARReportORM).where(SARReportORM.sar_ref == reference)
        result = await self.db.execute(stmt)
        report = result.scalar_one()

        report.status = "SOUMIS"
        report.submission_date = datetime.now(timezone.utc)
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
