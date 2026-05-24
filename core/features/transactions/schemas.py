from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tx_ref: str = Field(..., max_length=100)
    fabric_tx_id: str | None = Field(default=None, max_length=200)
    fabric_block_number: int | None = None

    tx_type: str = Field(..., max_length=50)
    asset_id: UUID
    initiator_id: UUID
    from_owner_id: UUID | None = None
    to_owner_id: UUID | None = None

    amount: Decimal | None = None
    settlement_date: datetime | None = None

    endorsing_orgs: list[str] | None = None
    regulatory_flag: bool
    justification: str | None = Field(default=None, max_length=500)
    created_at: datetime
