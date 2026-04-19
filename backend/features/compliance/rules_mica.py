import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import Settings
from backend.constants import MICA_IDENTIFICATION_THRESHOLD
from backend.core.redis_client import get_redis
from backend.features.transactions.models import NetworkEvent

logger = logging.getLogger(__name__)

MiCAArticle = Literal["ART68", "ART70", "ART76"]

@dataclass
class MiCAViolation:
    article: MiCAArticle
    description: str
    blocking: bool

@dataclass
class MiCAResult:
    compliant: bool
    violations: list[MiCAViolation]
    alert_ref: str | None
    identification_required: bool

class MiCAChecker:
    def __init__(self, settings: Settings, db: AsyncSession) -> None:
        self.settings = settings
        self.db = db

    async def check(self, transaction_amount: float, initiator_id: UUID, asset_id: str, asset_type: str) -> MiCAResult:
        violations: list[MiCAViolation] = []
        identification_required = False
        alert_ref = None

        if transaction_amount > MICA_IDENTIFICATION_THRESHOLD:
            identification_required = True

        if asset_type in ("OBLIGATION", "DERIVE"):
            if not asset_id.startswith("RWA-"):
                violations.append(MiCAViolation(
                    article="ART76",
                    description="Absence structurelle ISIN ou LEI identifiée (non conforme).",
                    blocking=False,
                ))

        if len(violations) > 0 and any(v.blocking for v in violations):
            year = datetime.now(timezone.utc).year
            try:
                redis_gen = get_redis()
                redis_conn = await redis_gen.__anext__()
                counter = await redis_conn.incr(f"mica:alert_counter:{year}")
                await redis_gen.aclose()
            except Exception:
                counter = 1
            alert_ref = f"TMA-{year}-{counter:03d}-MICA"

        compliant = not any(v.blocking for v in violations)

        event = NetworkEvent(
            event_name="MICA_VERIFICATION",
            fabric_tx_id="N/A",
            chaincode_name="rwa-token",
            fabric_block_number=0,
            payload={
                "asset_id": asset_id,
                "amount": transaction_amount,
                "compliant": compliant,
                "art68_triggered": identification_required,
            },
        )
        self.db.add(event)
        await self.db.commit()

        return MiCAResult(
            compliant=compliant,
            violations=violations,
            alert_ref=alert_ref,
            identification_required=identification_required,
        )
