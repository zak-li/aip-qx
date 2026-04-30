from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies import get_current_user, get_db, require_role
from backend.features.assets.models import Asset
from backend.features.auth.models import Organization, User

router = APIRouter()


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    first_name: str | None
    last_name: str | None
    role: str
    department: str | None
    employee_id: str | None
    phone: str | None
    msp_id: str | None
    mfa_enabled: bool
    is_active: bool
    org_id: UUID
    org_name: str | None = None
    org_country: str | None = None

@router.get("")
async def list_organizations(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, str]]:
    stmt = select(Organization).limit(limit).offset(offset)
    result = await db.execute(stmt)
    orgs = result.scalars().all()

    return [
        {
            "id": str(o.id),
            "name": o.name,
            "msp_id": o.msp_id,
            "status": o.status,
        }
        for o in orgs
    ]

_VALID_ROLES = {
    "EMETTEUR", "TRADER", "CUSTODIAN", "REGULATEUR",
    "AUDITEUR", "COMPLIANCE_OFFICER", "SUPER_ADMIN",
}

_VALID_COUNTRIES = {"FR", "GB", "MA", "DE", "US", "LU", "BE", "CH", "SG", "AE"}


@router.get("/users", response_model=list[UserSummary])
async def list_users(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    role: str | None = Query(default=None),
    country: str | None = Query(default=None),
    current_user: User = Depends(
        require_role("REGULATEUR", "COMPLIANCE_OFFICER", "SUPER_ADMIN", "AUDITEUR")
    ),
    db: AsyncSession = Depends(get_db),
) -> list[UserSummary]:
    from fastapi import HTTPException as _HTTPException
    if role and role.upper() not in _VALID_ROLES:
        raise _HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(sorted(_VALID_ROLES))}")
    if country and country.upper() not in _VALID_COUNTRIES:
        raise _HTTPException(status_code=400, detail="Invalid country code.")

    stmt = select(User, Organization).join(Organization, User.org_id == Organization.id)
    if role:
        stmt = stmt.where(User.role == role.upper())
    if country:
        stmt = stmt.where(Organization.country_code == country.upper())
    stmt = stmt.limit(limit).offset(offset)

    result = await db.execute(stmt)
    rows = result.all()

    users_out: list[UserSummary] = []
    for user, org in rows:
        users_out.append(
            UserSummary(
                id=user.id,
                email=user.email,
                first_name=user.first_name,
                last_name=user.last_name,
                role=user.role,
                department=user.department,
                employee_id=user.employee_id,
                phone=user.phone,
                msp_id=user.msp_id,
                mfa_enabled=user.mfa_enabled,
                is_active=user.is_active,
                org_id=user.org_id,
                org_name=org.legal_name,
                org_country=org.country_code,
            )
        )
    return users_out


@router.get("/{org_id}/portfolio")
async def get_portfolio(
    org_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str | int | float]:
    count_stmt = select(func.count(Asset.id)).where(
        Asset.issuer_org_id == org_id,
        Asset.status == "ACTIF",
    )
    count_result = await db.execute(count_stmt)
    active_count = count_result.scalar() or 0

    value_stmt = select(func.coalesce(func.sum(Asset.current_value), 0)).where(
        Asset.issuer_org_id == org_id,
        Asset.status != "REMBOURSE",
    )
    value_result = await db.execute(value_stmt)
    total_value = float(value_result.scalar() or 0)

    return {
        "org_id": str(org_id),
        "total_assets_value": total_value,
        "active_assets_count": active_count,
    }
