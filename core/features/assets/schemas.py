import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ASSET_NAME_MAX = 200
JUSTIFICATION_MAX = 500
REGULATORY_REF_MAX = 100

class TokenizeRequest(BaseModel):
    model_config = ConfigDict(strict=False)

    asset_id: str = Field(..., pattern=r"^RWA-[A-Z]{2,12}-[A-Z0-9]{2,8}-\d{4}-\d{3}$")
    isin: str = Field(..., min_length=12, max_length=12, pattern=r"^[A-Z]{2}[A-Z0-9]{10}$")
    asset_type: Literal[
        "OBLIGATION", "OPCVM", "IMMOBILIER", "DERIVE", "MATIERE_PREMIERE", "PRIVATE_EQUITY", "INFRASTRUCTURE"
    ]
    asset_name: str = Field(..., min_length=3, max_length=ASSET_NAME_MAX)
    issuer_lei: str = Field(..., min_length=20, max_length=20, pattern=r"^[A-Z0-9]{20}$")

    nominal_value: Decimal = Field(..., gt=0)
    currency: str = Field(..., min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    issuance_date: date
    justification: str = Field(..., min_length=10, max_length=JUSTIFICATION_MAX)

class TransferRequest(BaseModel):
    model_config = ConfigDict(strict=False)

    asset_id: str = Field(..., min_length=5, max_length=100)
    to_owner: str = Field(..., min_length=10, max_length=200)
    price: Decimal = Field(..., gt=0)
    justification: str = Field(..., min_length=10, max_length=JUSTIFICATION_MAX)

class FreezeRequest(BaseModel):
    model_config = ConfigDict(strict=False)

    asset_id: str = Field(..., min_length=5, max_length=100)
    reason: str = Field(..., min_length=10, max_length=JUSTIFICATION_MAX)
    regulatory_ref: str = Field(..., max_length=REGULATORY_REF_MAX, pattern=r"^[A-Z0-9]{2,8}-[A-Z]{2,4}-\d{4}-\d{3,}$")

class UnfreezeRequest(BaseModel):
    model_config = ConfigDict(strict=False)

    asset_id: str = Field(..., min_length=5, max_length=100)
    justification: str = Field(..., min_length=10, max_length=JUSTIFICATION_MAX)

class AssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    asset_id: str
    isin: str | None = None
    asset_type: str
    asset_name: str

    issuer_org_id: uuid.UUID | str
    current_owner_id: uuid.UUID | str

    @field_validator("issuer_org_id", "current_owner_id", mode="before")
    @classmethod
    def coerce_uuid_to_str(cls, v: uuid.UUID | str) -> str:
        return str(v)

    nominal_value: Decimal
    current_value: Decimal
    currency: str

    status: str
    issuance_date: date | str

    fabric_tx_id: str | None = None
    fabric_block_number: int | None = None

class ValuateRequest(BaseModel):
    model_config = ConfigDict(strict=False)

    current_value: Decimal = Field(..., gt=0, description="Nouvelle valeur courante de l'actif (NAV)")
    yield_to_maturity: Decimal | None = Field(default=None, ge=-1, le=1)
    duration: Decimal | None = Field(default=None, ge=0)
    convexity: Decimal | None = Field(default=None)
    credit_spread_bps: Decimal | None = Field(default=None, ge=0)
    pricing_source: str | None = Field(default=None, max_length=100)
    valuation_date: date | None = None

class ValuationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    asset_id: uuid.UUID
    valuation_date: date
    nav: Decimal
    yield_to_maturity: Decimal | None = None
    duration: Decimal | None = None
    convexity: Decimal | None = None
    credit_spread_bps: Decimal | None = None
    pricing_source: str | None = None

class ProvenanceRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    txID: str
    timestamp: str
    actorMSP: str
    actorDN: str
    action: str
    fromOwner: str | None = None
    toOwner: str | None = None
    amount: Decimal | None = None
    justification: str | None = None
    blockNumber: int | None = None
