from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database_base import Base


class ZKPCredential(Base):
    """Platform-issued eligibility credential (claim + ECDSA signature).

    The full credential (including signature) is returned once to the client
    and stored client-side only. The server keeps only the public key and
    revocation state.
    """
    __tablename__ = "zkp_credentials"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    public_key_x: Mapped[str] = mapped_column(Text, nullable=False)
    public_key_y: Mapped[str] = mapped_column(Text, nullable=False)

    age_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    kyc_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    not_sanctioned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    kyc_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    issuer_sig: Mapped[str] = mapped_column(Text, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False,
        server_default="now()",
    )


class ZKPNullifier(Base):
    """One-time proof token — prevents replay attacks on ZKP proofs."""
    __tablename__ = "zkp_nullifiers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    nullifier_hex: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    purpose: Mapped[str] = mapped_column(String(128), nullable=False)
    public_key_x: Mapped[str] = mapped_column(Text, nullable=False)
    used_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False,
        server_default="now()",
    )
