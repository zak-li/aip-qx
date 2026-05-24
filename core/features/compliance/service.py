"""Compliance orchestration service.

Used to instantiate KYC/Sanctions/AML/MiCA/SAR helpers per request, which
caused 5 short-lived objects + repeated fixture I/O on every transfer. The
helpers now hold no per-session state — settings is global, db is passed
to each method — so a single ComplianceService can be reused for the
lifetime of the process.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from core.config import settings as _settings
from core.constants import KYC_REQUIRED_LEVEL
from core.core.client_ip import get_request_ip
from core.features.compliance.aml import AMLResult, AMLScorer
from core.features.compliance.kyc import KYCResult, KYCVerifier
from core.features.compliance.models import AuditLog
from core.features.compliance.rules_mica import MiCAChecker, MiCAResult
from core.features.compliance.sanctions import SanctionsResult, SanctionsScreener
from core.features.compliance.sar_reporter import SARReporter

logger = logging.getLogger(__name__)


@dataclass
class ComplianceResult:
    approved: bool
    blocked_by: str | None
    blocking_reason: str | None
    kyc: KYCResult | None
    aml: AMLResult | None
    mica: MiCAResult | None
    sanctions: SanctionsResult | None
    sar_reference: str | None


class ComplianceService:
    """Orchestrate KYC → sanctions → AML → MiCA → SAR for a single request.

    The helper instances are reused across calls and only hold ``settings``
    (immutable). They take a ``db: AsyncSession`` parameter on each call,
    so this service can safely be a process-wide singleton without leaking
    request-scoped state.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        # Sanctions screener has no DB dependency; it can live for the whole
        # process lifetime.
        self._sanctions = SanctionsScreener(settings)

    async def full_check(
        self,
        db: AsyncSession,
        participant_id: UUID,
        amount: float,
        asset_id: str,
        asset_type: str,
        counterparty_id: UUID,
        full_name: str = "Unknown",
    ) -> ComplianceResult:
        start_time = time.time()

        kyc = KYCVerifier(self.settings, db)
        aml = AMLScorer(self.settings, db)
        mica = MiCAChecker(self.settings, db)
        sar = SARReporter(self.settings, db)

        try:
            kyc_res = await kyc.verify(participant_id, required_level=KYC_REQUIRED_LEVEL)
        except ValueError as exc:
            await self._log_block(db, participant_id, "COMPLIANCE_BLOCK", str(exc), start_time)
            raise

        if not kyc_res.approved:
            await self._log_block(db, participant_id, "COMPLIANCE_BLOCK", kyc_res.reason, start_time)
            return ComplianceResult(False, "KYC", kyc_res.reason, kyc_res, None, None, None, None)

        sanctions_res = await self._sanctions.screen(participant_id, full_name=full_name)
        if sanctions_res.hit:
            await self._log_block(
                db, participant_id, "COMPLIANCE_BLOCK",
                "Identifié dans les listes de sanctions/PEP", start_time,
            )
            return ComplianceResult(
                False, "SANCTIONS", "Correspondance trouvée explicitement",
                kyc_res, None, None, sanctions_res, None,
            )

        aml_res = await aml.score(participant_id, amount, counterparty_id)
        sar_ref = None
        if aml_res.blocked:
            if aml_res.sar_required:
                sar_ref = await sar.generate(participant_id, None, "AML_CRITICAL_THRESHOLD", amount)
            await self._log_block(
                db, participant_id, "COMPLIANCE_BLOCK",
                aml_res.blocked_reason or "Limites AML dépassées", start_time,
            )
            return ComplianceResult(False, "AML", aml_res.blocked_reason, kyc_res, aml_res, None, sanctions_res, sar_ref)

        mica_res = await mica.check(amount, participant_id, asset_id, asset_type)
        if not mica_res.compliant:
            await self._log_block(
                db, participant_id, "COMPLIANCE_BLOCK",
                "Vérifications MiCA échouées", start_time,
            )
            return ComplianceResult(
                False, "MICA", "Vérifications MiCA échouées",
                kyc_res, aml_res, mica_res, sanctions_res, None,
            )

        duration = int((time.time() - start_time) * 1000)
        logger.info(f"Compliance check PASS pour {participant_id} en {duration}ms")

        db.add(AuditLog(
            user_id=participant_id,
            endpoint="COMPLIANCE_PASS",
            http_method="VERIFY",
            ip_address=get_request_ip(),
            response_code=200,
            duration_ms=duration,
        ))
        await db.commit()

        return ComplianceResult(True, None, None, kyc_res, aml_res, mica_res, sanctions_res, None)

    @staticmethod
    async def _log_block(
        db: AsyncSession,
        user_id: UUID,
        action: str,
        justification: str,
        start_time: float,
    ) -> None:
        duration = int((time.time() - start_time) * 1000)
        logger.warning(
            "Compliance BLOCK %s pour %s en %dms: %s",
            action, user_id, duration, (justification or "")[:100],
        )

        db.add(AuditLog(
            user_id=user_id,
            endpoint=f"/{action}",
            http_method="BLOCK",
            ip_address=get_request_ip(),
            request_body={"justification": justification[:1000]} if justification else None,
            response_code=403,
            duration_ms=duration,
        ))
        await db.commit()


# Process-wide singleton — settings is immutable, helpers carry no per-request
# state, so this is safe to share across coroutines.
_singleton: ComplianceService | None = None
_singleton_lock = threading.Lock()


def get_compliance_service() -> ComplianceService:
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                _singleton = ComplianceService(_settings)
    return _singleton


async def full_check(
    participant_id: UUID,
    amount: float,
    asset_id: str,
    asset_type: str,
    counterparty_id: UUID,
    full_name: str,
    db: AsyncSession,
) -> tuple[bool, str, str]:
    """Module-level convenience wrapper used by features/assets/service.py."""
    svc = get_compliance_service()
    result = await svc.full_check(
        db=db,
        participant_id=participant_id,
        amount=amount,
        asset_id=asset_id,
        asset_type=asset_type,
        counterparty_id=counterparty_id,
        full_name=full_name,
    )
    if not result.approved:
        return True, result.blocking_reason or "Compliance check failed", result.blocked_by or "UNKNOWN"
    return False, "", ""
