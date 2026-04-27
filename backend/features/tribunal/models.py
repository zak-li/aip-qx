from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, String, Text, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database_base import Base

class TribunalSession(Base):
    __tablename__ = "tribunal_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id"), index=True, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    # States: COMMIT, REVEAL, RESOLVED
    status: Mapped[str] = mapped_column(String(20), default="COMMIT")

    # Outcome: None, FRAUD, LEGITIMATE
    final_decision: Mapped[str | None] = mapped_column(String(20), nullable=True)

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default="now()")
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

class TribunalVote(Base):
    __tablename__ = "tribunal_votes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tribunal_sessions.id"), nullable=False)
    auditor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)

    # Phase 1: Commit (Hash of vote + salt)
    commit_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # Phase 2: Reveal
    revealed_vote: Mapped[str | None] = mapped_column(String(20), nullable=True)
    revealed_salt: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Slashing
    reputation_staked: Mapped[float] = mapped_column(Float, default=100.0)
    slashed: Mapped[bool] = mapped_column(Boolean, default=False)
    rewarded: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default="now()")
