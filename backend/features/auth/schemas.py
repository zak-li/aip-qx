from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

EMAIL_MAX = 254
PASSWORD_MAX = 128
DEPARTMENT_MAX = 100

class LoginRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    email: EmailStr = Field(..., max_length=EMAIL_MAX)
    password: str = Field(..., min_length=8, max_length=PASSWORD_MAX)
    mfa_code: str | None = Field(default=None, min_length=6, max_length=6, pattern=r"^\d{6}$")

class TokenResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    mfa_required: bool = False

class UserProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    role: str = Field(..., max_length=50)
    org_id: UUID
    fabric_cert_serial: str | None = Field(default=None, max_length=200)
    department: str | None = Field(default=None, max_length=DEPARTMENT_MAX)
    mfa_enabled: bool = False

class MFASetupResponse(BaseModel):
    provisioning_uri: str
    secret: str

class MFAVerifyRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")
