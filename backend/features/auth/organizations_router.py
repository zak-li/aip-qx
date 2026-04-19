from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies import get_current_user, get_db
from backend.features.assets.models import Asset
from backend.features.auth.models import Organization, User

router = APIRouter()

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
