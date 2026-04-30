import logging
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.features.assets.models import Asset, AssetValuation

logger = logging.getLogger(__name__)

async def record_valuation(
    db: AsyncSession,
    asset_id: str,
    current_value: Decimal,
    yield_to_maturity: Decimal | None = None,
    duration: Decimal | None = None,
    convexity: Decimal | None = None,
    credit_spread_bps: Decimal | None = None,
    pricing_source: str | None = None,
    valuation_date: date | None = None,
) -> AssetValuation:
    stmt = select(Asset).where(Asset.asset_id == asset_id)
    result = await db.execute(stmt)
    asset = result.scalar_one_or_none()

    if not asset:
        raise ValueError(f"Actif {asset_id} introuvable pour la valorisation.")

    valuation = AssetValuation(
        asset_id=asset.id,
        valuation_date=valuation_date or date.today(),
        nav=current_value,
        yield_to_maturity=yield_to_maturity,
        duration=duration,
        convexity=convexity,
        credit_spread_bps=credit_spread_bps,
        pricing_source=pricing_source,
    )
    db.add(valuation)

    asset.current_value = current_value
    asset.updated_at = datetime.now(UTC).replace(tzinfo=None)

    await db.commit()
    await db.refresh(valuation)

    logger.info(f"Valorisation enregistrée pour {asset_id}: {current_value}")
    return valuation

async def get_history(db: AsyncSession, asset_id: str) -> list[AssetValuation]:
    stmt = (
        select(AssetValuation)
        .join(Asset, Asset.id == AssetValuation.asset_id)
        .where(Asset.asset_id == asset_id)
        .order_by(AssetValuation.valuation_date.desc(), AssetValuation.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())

