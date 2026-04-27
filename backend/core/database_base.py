from __future__ import annotations

import uuid
from datetime import datetime, UTC

from sqlalchemy import MetaData, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=convention)

class Base(DeclarativeBase):
    metadata = metadata
    type_annotation_map = {
        uuid.UUID: UUID(as_uuid=True)
    }

class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"), nullable=False
    )

class TimestampUpdateMixin(TimestampMixin):
    updated_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"),
        onupdate=lambda: datetime.now(UTC).replace(tzinfo=None),
        nullable=False,
    )
