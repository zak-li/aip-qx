from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, Numeric, String, ForeignKey, Enum, Integer
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database_base import Base, UUIDMixin, TimestampMixin
from backend.features.assets.models import Asset
from backend.features.auth.models import User

JsonType = JSONB
ArrayType = ARRAY(String)

class Transaction(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "transactions"

    tx_ref: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    fabric_tx_id: Mapped[str | None] = mapped_column(String, unique=True, index=True, nullable=True)
    fabric_block_number: Mapped[int | None] = mapped_column(nullable=True)
    fabric_channel: Mapped[str] = mapped_column(String, server_default="'rwa-channel'", nullable=False, default="rwa-channel")
    chaincode_name: Mapped[str] = mapped_column(String, server_default="'rwa-token'", nullable=False, default="rwa-token")

    tx_type: Mapped[str] = mapped_column(
        Enum('TOKENISATION', 'TRANSFERT', 'GEL', 'DEGEL', 'RACHAT', 'COUPON_PAIEMENT', 'MISE_A_JOUR_VALEUR', 'ANNULATION', 'REGLEMENT', name="transaction_types", create_type=False),
        nullable=False,
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id"), index=True, nullable=False)
    initiator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    from_owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    to_owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), server_default="'EUR'", nullable=True, default="EUR")
    exchange_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    settlement_date: Mapped[datetime | None] = mapped_column(nullable=True)
    clearing_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)

    endorsing_orgs: Mapped[list[str] | None] = mapped_column(ArrayType, nullable=True)
    endorsement_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    justification: Mapped[str | None] = mapped_column(String, nullable=True)
    
    regulatory_flag: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False, default=False)
    sar_generated: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(30), server_default="'CONFIRME'", nullable=False, default="CONFIRME")
    processing_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    asset: Mapped[Asset] = relationship("Asset", foreign_keys=[asset_id], lazy="selectin")
    initiator: Mapped[User] = relationship("User", foreign_keys=[initiator_id], lazy="selectin")

class NetworkEvent(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "network_events"

    event_name: Mapped[str] = mapped_column(String, index=True, nullable=False)
    chaincode_name: Mapped[str] = mapped_column(String, nullable=False)
    fabric_tx_id: Mapped[str] = mapped_column(String, nullable=False)
    fabric_block_number: Mapped[int] = mapped_column(nullable=False)

    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=False)
    processed: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False, default=False)
    processed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    error_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False, default=0)
