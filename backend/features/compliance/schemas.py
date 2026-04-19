from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

class ComplianceStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    participant_id: UUID
    kyc_level: int
    kyc_status: str = Field(..., max_length=50)
    aml_score: Decimal
    risk_category: str = Field(..., max_length=50)
    expires_at: datetime

class AMLResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    score: Decimal
    risk_category: str = Field(..., max_length=50)
    blocked: bool
    indicators: list[str]
