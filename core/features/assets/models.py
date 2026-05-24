from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.core.database_base import Base, TimestampUpdateMixin, UUIDMixin
from core.features.auth.models import Organization, User


class Asset(Base, UUIDMixin, TimestampUpdateMixin):
    __tablename__ = "assets"

    asset_id: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    isin: Mapped[str | None] = mapped_column(String, nullable=True)
    asset_type: Mapped[str] = mapped_column(
        Enum(
            "OBLIGATION", "OPCVM", "IMMOBILIER", "DERIVE",
            "MATIERE_PREMIERE", "PRIVATE_EQUITY", "INFRASTRUCTURE",
            name="asset_type_enum",
            create_type=False,
        ),
        nullable=False,
    )
    asset_name: Mapped[str] = mapped_column(String(200), nullable=False)
    figi: Mapped[str | None] = mapped_column(String(12), nullable=True)
    cusip: Mapped[str | None] = mapped_column(String(9), nullable=True)
    sedol: Mapped[str | None] = mapped_column(String(7), nullable=True)

    issuer_org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=False)
    current_owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)

    nominal_value: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    current_value: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    status: Mapped[str] = mapped_column(
        Enum("ACTIF", "GELE", "EN_EMISSION", "REMBOURSE", name="asset_status_enum", create_type=False),
        index=True,
        nullable=False,
    )
    issuance_date: Mapped[date] = mapped_column(Date, nullable=False)
    maturity_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    coupon_rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    coupon_frequency: Mapped[str | None] = mapped_column(String(20), nullable=True)
    rating_moodys: Mapped[str | None] = mapped_column(String(10), nullable=True)
    rating_sp: Mapped[str | None] = mapped_column(String(10), nullable=True)
    rating_fitch: Mapped[str | None] = mapped_column(String(10), nullable=True)
    underlying_asset: Mapped[str | None] = mapped_column(Text, nullable=True)
    prospectus_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)

    fabric_tx_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    fabric_block_number: Mapped[int | None] = mapped_column(nullable=True)
    last_valuation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    total_transfers: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False, default=0)
    is_fractionalized: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False, default=False)
    fraction_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_col: Mapped[dict | None] = mapped_column("metadata", JSONB, server_default=text("'{}'::jsonb"), nullable=True)

    issuer_org: Mapped[Organization] = relationship("Organization", foreign_keys=[issuer_org_id], lazy="selectin")
    current_owner: Mapped[User | None] = relationship("User", foreign_keys=[current_owner_id], lazy="selectin")

class AssetValuation(Base, UUIDMixin, TimestampUpdateMixin):
    __tablename__ = "asset_valuations"

    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id"), index=True, nullable=False)
    valuation_date: Mapped[date] = mapped_column(Date, nullable=False)

    nav: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    nav_currency: Mapped[str] = mapped_column(String(3), server_default="'EUR'", nullable=False, default="EUR")
    yield_to_maturity: Mapped[Decimal | None] = mapped_column(Numeric(8, 6), nullable=True)
    duration: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    convexity: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    credit_spread_bps: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    valuation_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    pricing_source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    validated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
