from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

DEPARTMENT_MAX = 100


class OIDCTokenResponse(BaseModel):
    """Returned after a successful OIDC callback / token refresh."""
    model_config = ConfigDict(strict=True)

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_expires_in: int = 0


class UserProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    role: str = Field(..., max_length=50)
    org_id: UUID
    fabric_cert_serial: str | None = Field(default=None, max_length=200)
    department: str | None = Field(default=None, max_length=DEPARTMENT_MAX)
    keycloak_sub: str | None = None
