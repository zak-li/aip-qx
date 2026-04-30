"""gRPC servicer for the Compliance service."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import grpc
import grpc.aio
from sqlalchemy import or_, select

from backend.config import settings
from backend.core.database import AsyncSessionLocal
from backend.features.compliance.aml import AMLScorer
from backend.features.compliance.kyc import KYCVerifier
from backend.features.compliance.models import ComplianceRecord, KYCDocument, SARReport
from backend.features.compliance.sar_reporter import SARReporter
from backend.grpc_generated import compliance_pb2, compliance_pb2_grpc


class ComplianceServicer(compliance_pb2_grpc.ComplianceServiceServicer):

    async def ListComplianceRecords(
        self,
        request: compliance_pb2.PaginationRequest,
        context: grpc.aio.ServicerContext,
    ) -> compliance_pb2.ComplianceList:
        async with AsyncSessionLocal() as db:
            stmt = select(ComplianceRecord).limit(request.limit or 50).offset(request.offset or 0)
            records = (await db.execute(stmt)).scalars().all()
        return compliance_pb2.ComplianceList(
            records=[_record_to_proto(r) for r in records]
        )

    async def GetActiveAlerts(
        self,
        request: compliance_pb2.PaginationRequest,
        context: grpc.aio.ServicerContext,
    ) -> compliance_pb2.AlertList:
        async with AsyncSessionLocal() as db:
            risk_stmt = (
                select(ComplianceRecord)
                .where(or_(
                    ComplianceRecord.risk_category.in_(["ELEVE", "CRITIQUE"]),
                    ComplianceRecord.sanctions_hit,
                    ComplianceRecord.pep_status,
                ))
                .limit(request.limit or 50)
                .offset(request.offset or 0)
            )
            risk_records = (await db.execute(risk_stmt)).scalars().all()

            sar_stmt = select(SARReport).where(SARReport.status == "DRAFT").limit(request.limit or 50)
            sar_records = (await db.execute(sar_stmt)).scalars().all()

        alerts = [
            compliance_pb2.Alert(
                type="HIGH_RISK_PARTICIPANT",
                participant_id=str(r.participant_id),
                risk_category=r.risk_category or "",
                aml_score=float(r.aml_score or 0),
                sanctions_hit=bool(r.sanctions_hit),
                pep_status=bool(r.pep_status),
                expires_at=r.expires_at.isoformat() if r.expires_at else "",
            )
            for r in risk_records
        ] + [
            compliance_pb2.Alert(
                type="DRAFT_SAR",
                participant_id=str(s.reported_user_id),
                sar_ref=s.sar_ref or "",
                reason_code=s.reason_code or "",
                amount=float(s.amount_involved or 0),
            )
            for s in sar_records
        ]

        return compliance_pb2.AlertList(alerts=alerts)

    async def GetComplianceStatus(
        self,
        request: compliance_pb2.UserIdRequest,
        context: grpc.aio.ServicerContext,
    ) -> compliance_pb2.ComplianceStatus:
        async with AsyncSessionLocal() as db:
            stmt = select(ComplianceRecord).where(
                ComplianceRecord.participant_id == UUID(request.user_id)
            )
            record = (await db.execute(stmt)).scalar_one_or_none()

        if not record:
            await context.abort(grpc.StatusCode.NOT_FOUND, "Compliance record not found")
        return _record_to_proto(record)

    async def SubmitKYC(
        self,
        request: compliance_pb2.KYCSubmitRequest,
        context: grpc.aio.ServicerContext,
    ) -> compliance_pb2.KYCSubmitResponse:
        async with AsyncSessionLocal() as db:
            user_uuid = UUID(request.user_id)
            doc = KYCDocument(
                user_id=user_uuid,
                document_type=request.document_type,
                file_hash=request.file_hash,
                document_number=request.document_number or None,
                issuing_country=request.issuing_country or None,
                verified=False,
            )
            db.add(doc)

            stmt = select(ComplianceRecord).where(ComplianceRecord.participant_id == user_uuid)
            record = (await db.execute(stmt)).scalar_one_or_none()
            caller_id = UUID(context.user_payload["sub"])

            if record:
                record.kyc_status = "EN_COURS"
                record.checked_by = caller_id
                record.check_date = datetime.now(UTC)
            else:
                record = ComplianceRecord(
                    participant_id=user_uuid,
                    kyc_status="EN_COURS",
                    kyc_level=1,
                    aml_score=Decimal("0"),
                    risk_category="FAIBLE",
                    checked_by=caller_id,
                    check_date=datetime.now(UTC),
                    expires_at=datetime.now(UTC) + timedelta(days=365),
                )
                db.add(record)

            await db.commit()

        return compliance_pb2.KYCSubmitResponse(
            message="Document KYC soumis. Dossier en cours de vérification.",
            document_type=request.document_type,
        )

    async def ApproveKYC(
        self,
        request: compliance_pb2.KYCApproveRequest,
        context: grpc.aio.ServicerContext,
    ) -> compliance_pb2.KYCApproveResponse:
        async with AsyncSessionLocal() as db:
            user_uuid = UUID(request.user_id)
            stmt = select(ComplianceRecord).where(ComplianceRecord.participant_id == user_uuid)
            record = (await db.execute(stmt)).scalar_one_or_none()

            if not record:
                await context.abort(grpc.StatusCode.NOT_FOUND, "Compliance record not found")

            now = datetime.now(UTC)
            record.kyc_status = "VERIFIE"
            record.kyc_level = request.level
            record.approved_by = UUID(context.user_payload["sub"])
            record.check_date = now
            record.expires_at = now + timedelta(days=request.validity_days or 365)
            if request.notes:
                record.notes = request.notes
            await db.commit()

            verifier = KYCVerifier(settings, db)
            kyc_result = await verifier.verify(user_uuid)

        return compliance_pb2.KYCApproveResponse(
            message=f"KYC approuvé au niveau {request.level}.",
            kyc_status=record.kyc_status,
            expires_at=record.expires_at.isoformat(),
            needs_renewal=kyc_result.needs_renewal,
        )

    async def RunAMLScreening(
        self,
        request: compliance_pb2.AMLScreeningRequest,
        context: grpc.aio.ServicerContext,
    ) -> compliance_pb2.AMLResult:
        async with AsyncSessionLocal() as db:
            scorer = AMLScorer(settings, db)
            aml_result = await scorer.score(
                UUID(request.user_id),
                request.amount,
                UUID(request.counterparty_id),
            )
            if aml_result.sar_required:
                reporter = SARReporter(settings, db)
                await reporter.generate(
                    participant_id=UUID(request.user_id),
                    tx_id=None,
                    reason_code="AML_CRITICAL_THRESHOLD",
                    amount=request.amount,
                    regulatory_ref=None,
                )

        return compliance_pb2.AMLResult(
            score=float(aml_result.score),
            risk_category=aml_result.risk_category,
            blocked=aml_result.blocked,
            indicators=list(aml_result.indicators or []),
        )


# ---------------------------------------------------------------------------

def _record_to_proto(r: ComplianceRecord) -> compliance_pb2.ComplianceStatus:
    return compliance_pb2.ComplianceStatus(
        participant_id=str(r.participant_id),
        kyc_status=r.kyc_status or "",
        kyc_level=r.kyc_level or 0,
        aml_score=float(r.aml_score or 0),
        risk_category=r.risk_category or "",
        sanctions_hit=bool(r.sanctions_hit),
        pep_status=bool(r.pep_status),
        expires_at=r.expires_at.isoformat() if r.expires_at else "",
    )
