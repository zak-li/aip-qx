from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import TIMESTAMP, Boolean, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database_base import Base, TimestampMixin, UUIDMixin


class ComplianceRecord(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "compliance_records"

    participant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    kyc_status: Mapped[str] = mapped_column(String, server_default="'NON_INITIE'", nullable=False, default='NON_INITIE')
    kyc_level: Mapped[int] = mapped_column(Integer, server_default="1", nullable=False, default=1)
    aml_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), server_default="0", nullable=False, default=Decimal("0"))
    risk_category: Mapped[str] = mapped_column(String, server_default="'FAIBLE'", nullable=False, default='FAIBLE')

    sanctions_screened: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False, default=False)
    sanctions_hit: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False, default=False)
    pep_status: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False, default=False)
    adverse_media: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False, default=False)
    sar_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False, default=0)

    check_provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    check_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    documents_verified: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)

    checked_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    check_date: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), index=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    user = relationship("User", foreign_keys=[participant_id], lazy="selectin")

    @property
    def is_expired(self) -> bool:
        return datetime.now(UTC) >= self.expires_at

    def needs_renewal(self) -> bool:
        return self.is_expired or self.kyc_status == "EXPIRE"

class SARReport(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "sar_reports"

    sar_ref: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("transactions.id"), index=True, nullable=True)
    reported_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    reporting_officer: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)

    reason_code: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_description: Mapped[str] = mapped_column(Text, nullable=False)
    amount_involved: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)

    submitted_to: Mapped[str] = mapped_column(String(100), nullable=False)
    submission_date: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    acknowledgement_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)

    is_tipping_off_risk: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(30), server_default="'DRAFT'", nullable=False, default='DRAFT')

class AuditLog(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "audit_logs"

    trace_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    org_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    endpoint: Mapped[str] = mapped_column(String, nullable=False)
    http_method: Mapped[str] = mapped_column(String, nullable=False)
    ip_address: Mapped[str] = mapped_column(String, nullable=False)

    request_body: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    response_code: Mapped[int] = mapped_column(Integer, nullable=False)
    fabric_tx_id: Mapped[str | None] = mapped_column(String, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)

class KYCDocument(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "kyc_documents"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    document_type: Mapped[str] = mapped_column(String(50), nullable=False)
    document_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    issuing_country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    issued_date: Mapped[datetime | None] = mapped_column(nullable=True)
    expiry_date: Mapped[datetime | None] = mapped_column(nullable=True)
    file_hash: Mapped[str] = mapped_column(String(128), nullable=False)

    verified: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False, default=False)
    verified_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
