import logging
import time
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.features.compliance.aml import AMLResult, AMLScorer
from backend.features.compliance.kyc import KYCResult, KYCVerifier
from backend.features.compliance.rules_mica import MiCAChecker, MiCAResult
from backend.features.compliance.sanctions import SanctionsResult, SanctionsScreener
from backend.features.compliance.sar_reporter import SARReporter
from backend.config import Settings
from backend.constants import KYC_REQUIRED_LEVEL
from backend.features.compliance.models import AuditLog

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
    def __init__(self, settings: Settings, db: AsyncSession) -> None:
        self.settings = settings
        self.db = db

    async def full_check(
        self, participant_id: UUID, amount: float, asset_id: str, asset_type: str, counterparty_id: UUID, full_name: str = "Unknown"
    ) -> ComplianceResult:
        start_time = time.time()

        kyc_verifier = KYCVerifier(self.settings, self.db)
        sanctions_screener = SanctionsScreener(self.settings)
        aml_scorer = AMLScorer(self.settings, self.db)
        mica_checker = MiCAChecker(self.settings, self.db)
        sar_reporter = SARReporter(self.settings, self.db)

        try:
            kyc_res = await kyc_verifier.verify(participant_id, required_level=KYC_REQUIRED_LEVEL)
        except ValueError as exc:
            await self._log_block(participant_id, "COMPLIANCE_BLOCK", str(exc), start_time)
            raise

        if not kyc_res.approved:
            await self._log_block(participant_id, "COMPLIANCE_BLOCK", kyc_res.reason, start_time)
            return ComplianceResult(False, "KYC", kyc_res.reason, kyc_res, None, None, None, None)

        sanctions_res = await sanctions_screener.screen(participant_id, full_name=full_name)
        if sanctions_res.hit:
            await self._log_block(participant_id, "COMPLIANCE_BLOCK", "Identifié dans les listes de sanctions/PEP", start_time)
            return ComplianceResult(False, "SANCTIONS", "Correspondance trouvée explicitement", kyc_res, None, None, sanctions_res, None)

        aml_res = await aml_scorer.score(participant_id, amount, counterparty_id)
        sar_ref = None
        if aml_res.blocked:
            if aml_res.sar_required:
                sar_ref = await sar_reporter.generate(participant_id, None, "AML_CRITICAL_THRESHOLD", amount)
            await self._log_block(participant_id, "COMPLIANCE_BLOCK", aml_res.blocked_reason or "Limites AML dépassées", start_time)
            return ComplianceResult(False, "AML", aml_res.blocked_reason, kyc_res, aml_res, None, sanctions_res, sar_ref)

        mica_res = await mica_checker.check(amount, participant_id, asset_id, asset_type)
        if not mica_res.compliant:
            await self._log_block(participant_id, "COMPLIANCE_BLOCK", "Vérifications MiCA échouées", start_time)
            return ComplianceResult(False, "MICA", "Vérifications MiCA échouées", kyc_res, aml_res, mica_res, sanctions_res, None)

        duration = int((time.time() - start_time) * 1000)
        logger.info(f"Compliance check PASS pour {participant_id} en {duration}ms")

        log = AuditLog(
            user_id=participant_id,
            endpoint="COMPLIANCE_PASS",
            http_method="VERIFY",
            ip_address="127.0.0.1",
            response_code=200,
            duration_ms=duration,
        )
        self.db.add(log)
        await self.db.commit()

        return ComplianceResult(True, None, None, kyc_res, aml_res, mica_res, sanctions_res, None)

    async def _log_block(self, user_id: UUID, action: str, justification: str, start_time: float) -> None:
        duration = int((time.time() - start_time) * 1000)
        logger.warning(f"Compliance BLOCK {action} pour {user_id} en {duration}ms: {justification[:100]}")

        log = AuditLog(
            user_id=user_id,
            endpoint=f"/{action}",
            http_method="BLOCK",
            ip_address=justification[:255] if justification else "N/A",
            response_code=403,
            duration_ms=duration,
        )
        self.db.add(log)
        await self.db.commit()

async def full_check(
    participant_id: "UUID",
    amount: float,
    asset_id: str,
    asset_type: str,
    counterparty_id: "UUID",
    full_name: str,
    db: "AsyncSession",
) -> tuple[bool, str, str]:
    from backend.config import settings as _settings

    svc = ComplianceService(_settings, db)
    result = await svc.full_check(
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
