from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import Settings
from backend.constants import KYC_RENEWAL_DAYS, KYC_REQUIRED_LEVEL
from backend.features.compliance.models import ComplianceRecord, KYCDocument

@dataclass
class KYCResult:
    approved: bool
    level: int
    kyc_status: str
    expires_at: datetime
    reason: str
    needs_renewal: bool

class KYCVerifier:
    def __init__(self, settings: Settings, db: AsyncSession) -> None:
        self.settings = settings
        self.db = db

    async def verify(self, user_id: UUID, required_level: int = KYC_REQUIRED_LEVEL) -> KYCResult:
        stmt = select(ComplianceRecord).where(
            ComplianceRecord.participant_id == user_id
        ).order_by(ComplianceRecord.created_at.desc()).limit(1)

        result = await self.db.execute(stmt)
        record = result.scalar_one_or_none()

        now = datetime.now(timezone.utc)

        if not record:
            raise ValueError(f"Aucun dossier KYC trouvé pour l'utilisateur {user_id}")

        if record.expires_at < now:
            return KYCResult(
                approved=False, level=record.kyc_level, kyc_status=record.kyc_status,
                expires_at=record.expires_at, reason=f"KYC expiré le {record.expires_at.date()}",
                needs_renewal=True,
            )

        renewal_threshold = now + timedelta(days=KYC_RENEWAL_DAYS)

        if record.kyc_level < required_level:
            return KYCResult(
                approved=False, level=record.kyc_level, kyc_status=record.kyc_status,
                expires_at=record.expires_at, reason=f"Niveau {record.kyc_level} insuffisant (requis: {required_level})",
                needs_renewal=(record.expires_at < renewal_threshold),
            )

        return KYCResult(
            approved=True, level=record.kyc_level, kyc_status=record.kyc_status,
            expires_at=record.expires_at, reason="Score et niveau conformes.",
            needs_renewal=(record.expires_at < renewal_threshold),
        )

    async def get_documents(self, user_id: UUID) -> list[KYCDocument]:
        stmt = select(KYCDocument).where(KYCDocument.user_id == user_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
