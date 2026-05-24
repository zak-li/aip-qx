from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.dependencies import get_current_user, get_db
from core.features.auth.models import User
from core.features.transactions.models import Transaction
from core.features.transactions.schemas import TransactionResponse

router = APIRouter()

@router.get("", response_model=list[TransactionResponse])
async def list_transactions(
    tx_type: str | None = None,
    org_id: str | None = None,
    regulatory_flag: bool | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Transaction]:
    stmt = select(Transaction)

    if tx_type:
        stmt = stmt.where(Transaction.tx_type == tx_type)
    if regulatory_flag is not None:
        stmt = stmt.where(Transaction.regulatory_flag == regulatory_flag)

    stmt = stmt.order_by(Transaction.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    return list(result.scalars().all())

@router.get("/stats/summary")
async def get_transaction_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, int | float]:
    total_stmt = select(func.count(Transaction.id))
    total_result = await db.execute(total_stmt)
    total = total_result.scalar() or 0

    frozen_stmt = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
        Transaction.tx_type == "GEL"
    )
    frozen_result = await db.execute(frozen_stmt)
    volume_frozen = float(frozen_result.scalar() or 0)

    return {"total_transactions": total, "volume_frozen": volume_frozen}

@router.get("/{tx_ref}", response_model=TransactionResponse)
async def get_transaction(
    tx_ref: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Transaction:
    stmt = select(Transaction).where(Transaction.tx_ref == tx_ref)
    result = await db.execute(stmt)
    tx = result.scalar_one_or_none()

    if not tx:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction introuvable.")

    return tx
