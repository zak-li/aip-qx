from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database_base import Base, UUIDMixin


def _now_utc() -> datetime:
    return datetime.now(UTC)

class Organization(Base, UUIDMixin):
    __tablename__ = "organizations"

    org_code: Mapped[str] = mapped_column(String, nullable=False)
    legal_name: Mapped[str] = mapped_column(String, nullable=False)
    short_name: Mapped[str | None] = mapped_column(String, nullable=True)
    org_type: Mapped[str] = mapped_column(String, nullable=False)
    lei: Mapped[str | None] = mapped_column(String, nullable=True)
    bic_swift: Mapped[str | None] = mapped_column(String, nullable=True)
    msp_id: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    country_code: Mapped[str | None] = mapped_column(String, nullable=True)
    jurisdiction: Mapped[str | None] = mapped_column(String, nullable=True)
    regulator_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    aml_risk_rating: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)
    onboarded_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_audit_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"),
        onupdate=_now_utc,
        nullable=False,
    )

    users: Mapped[list[User]] = relationship("User", back_populates="organization", lazy="selectin")

    @property
    def name(self) -> str:
        return self.legal_name

    @property
    def bic(self) -> str | None:
        return self.bic_swift

    @property
    def country(self) -> str | None:
        return self.country_code

    @property
    def status(self) -> str:
        return "ACTIF" if self.is_active else "INACTIF"

class User(Base, UUIDMixin):
    __tablename__ = "users"

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    first_name: Mapped[str | None] = mapped_column(String, nullable=True)
    last_name: Mapped[str | None] = mapped_column(String, nullable=True)
    role: Mapped[str] = mapped_column(
        Enum(
            "EMETTEUR", "TRADER", "CUSTODIAN", "REGULATEUR",
            "AUDITEUR", "COMPLIANCE_OFFICER", "SUPER_ADMIN",
            name="user_role_enum",
            create_type=False,
        ),
        nullable=False,
    )
    msp_id: Mapped[str | None] = mapped_column(String, nullable=True)
    fabric_cert_serial: Mapped[str | None] = mapped_column(String, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    department: Mapped[str | None] = mapped_column(String, nullable=True)
    employee_id: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    mfa_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(nullable=True)
    last_login: Mapped[datetime | None] = mapped_column(nullable=True)
    password_changed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"),
        onupdate=_now_utc,
        nullable=False,
    )
    organization: Mapped[Organization] = relationship("Organization", back_populates="users", lazy="selectin")

    @property
    def is_locked(self) -> bool:
        if not self.locked_until:
            return False
        return datetime.now(UTC) <= self.locked_until

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} role={self.role}>"

