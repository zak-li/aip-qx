from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.features.compliance.aml import AMLScorer
from backend.features.compliance.kyc import KYCVerifier
from backend.features.compliance.sar_reporter import SARReporter
from backend.config import settings
from backend.dependencies import get_db, require_role
from backend.features.compliance.models import ComplianceRecord, KYCDocument, SARReport
from backend.features.auth.models import User
from backend.features.compliance.schemas import AMLResult, ComplianceStatusResponse

router = APIRouter()


class KYCSubmitRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    user_id: UUID
    document_type: str = Field(..., max_length=50)
    file_hash: str = Field(..., min_length=32, max_length=128)
    document_number: str | None = Field(default=None, max_length=100)
    issuing_country: str | None = Field(default=None, min_length=2, max_length=2)


class KYCApproveRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    user_id: UUID
    level: int = Field(..., ge=1, le=5)
    validity_days: int = Field(default=365, ge=30, le=1095)
    notes: str | None = Field(default=None, max_length=1000)


class AMLScreeningRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    user_id: UUID
    amount: float = Field(..., gt=0)
    counterparty_id: UUID


@router.get("")
async def list_compliance_records(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_role("COMPLIANCE_OFFICER", "REGULATEUR", "SUPER_ADMIN", "AUDITEUR", "EMETTEUR")),
    db: AsyncSession = Depends(get_db),
) -> list[ComplianceStatusResponse]:
    stmt = select(ComplianceRecord).limit(limit).offset(offset)
    result = await db.execute(stmt)
    records = result.scalars().all()
    return list(records)


@router.get("/alerts/active")
async def get_active_alerts(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_role("COMPLIANCE_OFFICER", "REGULATEUR", "EMETTEUR")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    high_risk_stmt = (
        select(ComplianceRecord)
        .where(
            or_(
                ComplianceRecord.risk_category.in_(["ELEVE", "CRITIQUE"]),
                ComplianceRecord.sanctions_hit,
                ComplianceRecord.pep_status,
            )
        )
        .limit(limit)
        .offset(offset)
    )
    risk_res = await db.execute(high_risk_stmt)
    risk_records = risk_res.scalars().all()

    sar_stmt = select(SARReport).where(SARReport.status == "DRAFT").limit(limit)
    sar_res = await db.execute(sar_stmt)
    sar_records = sar_res.scalars().all()

    alerts: list[dict] = []

    for rec in risk_records:
        alerts.append({
            "type": "HIGH_RISK_PARTICIPANT",
            "participant_id": str(rec.participant_id),
            "risk_category": rec.risk_category,
            "aml_score": str(rec.aml_score),
            "sanctions_hit": rec.sanctions_hit,
            "pep_status": rec.pep_status,
            "expires_at": rec.expires_at.isoformat(),
        })

    for sar in sar_records:
        alerts.append({
            "type": "DRAFT_SAR",
            "sar_ref": sar.sar_ref,
            "participant_id": str(sar.reported_user_id),
            "reason_code": sar.reason_code,
            "amount": str(sar.amount_involved or 0),
            "created_at": sar.created_at.isoformat() if hasattr(sar, "created_at") and sar.created_at else None,
        })

    return alerts


@router.get("/{user_id}", response_model=ComplianceStatusResponse)
async def get_compliance_status(
    user_id: UUID,
    current_user: User = Depends(require_role("COMPLIANCE_OFFICER", "REGULATEUR")),
    db: AsyncSession = Depends(get_db),
) -> ComplianceRecord:
    stmt = select(ComplianceRecord).where(ComplianceRecord.participant_id == user_id)
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dossier compliance introuvable.")

    return record


@router.post("/kyc/submit", status_code=201)
async def submit_kyc(
    body: KYCSubmitRequest,
    current_user: User = Depends(require_role("COMPLIANCE_OFFICER")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    doc = KYCDocument(
        user_id=body.user_id,
        document_type=body.document_type,
        file_hash=body.file_hash,
        document_number=body.document_number,
        issuing_country=body.issuing_country,
        verified=False,
    )
    db.add(doc)

    stmt = select(ComplianceRecord).where(ComplianceRecord.participant_id == body.user_id)
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()

    if record:
        record.kyc_status = "EN_COURS"
        record.checked_by = current_user.id
        record.check_date = datetime.now(timezone.utc)
    else:
        record = ComplianceRecord(
            participant_id=body.user_id,
            kyc_status="EN_COURS",
            kyc_level=1,
            aml_score=Decimal("0"),
            risk_category="FAIBLE",
            checked_by=current_user.id,
            check_date=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=365),
        )
        db.add(record)

    await db.commit()
    return {"message": "Document KYC soumis. Dossier en cours de vérification.", "document_type": body.document_type}


@router.post("/kyc/approve")
async def approve_kyc(
    body: KYCApproveRequest,
    current_user: User = Depends(require_role("COMPLIANCE_OFFICER")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    stmt = select(ComplianceRecord).where(ComplianceRecord.participant_id == body.user_id)
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dossier compliance introuvable.")

    now = datetime.now(timezone.utc)
    record.kyc_status = "VERIFIE"
    record.kyc_level = body.level
    record.approved_by = current_user.id
    record.check_date = now
    record.expires_at = now + timedelta(days=body.validity_days)
    if body.notes:
        record.notes = body.notes

    await db.commit()

    verifier = KYCVerifier(settings, db)
    kyc_result = await verifier.verify(body.user_id)

    return {
        "message": f"KYC approuvé au niveau {body.level}.",
        "kyc_status": record.kyc_status,
        "expires_at": record.expires_at.isoformat(),
        "needs_renewal": str(kyc_result.needs_renewal),
    }


@router.post("/screening/run", response_model=AMLResult)
async def run_aml_screening(
    body: AMLScreeningRequest,
    current_user: User = Depends(require_role("COMPLIANCE_OFFICER")),
    db: AsyncSession = Depends(get_db),
) -> AMLResult:
    scorer = AMLScorer(settings, db)
    aml_result = await scorer.score(body.user_id, body.amount, body.counterparty_id)

    if aml_result.sar_required:
        reporter = SARReporter(settings, db)
        await reporter.generate(
            participant_id=body.user_id,
            tx_id=None,
            reason_code="AML_CRITICAL_THRESHOLD",
            amount=body.amount,
            regulatory_ref=None,
        )

    return AMLResult(
        score=Decimal(str(aml_result.score)),
        risk_category=aml_result.risk_category,
        blocked=aml_result.blocked,
        indicators=aml_result.indicators,
    )
