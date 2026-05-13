import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.redis_client import get_redis
from backend.dependencies import get_fabric
from backend.exceptions import AssetFrozenError, AssetNotFoundException, ComplianceBlockedError
from backend.features.assets.models import Asset
from backend.features.assets.schemas import (
    AssetResponse,
    FreezeRequest,
    TokenizeRequest,
    TransferRequest,
    UnfreezeRequest,
)
from backend.features.auth.models import Organization, User
from backend.features.compliance.service import full_check
from backend.features.fraud_detection.neo4j_sync import get_neo4j_client
from backend.features.transactions.models import Transaction

logger = logging.getLogger(__name__)


async def _publish_event(channel: str, message: str) -> None:
    """Publish an event to a Redis channel. Non-blocking — failures are logged and swallowed."""
    try:
        redis_gen = get_redis()
        redis_conn = await redis_gen.__anext__()
        await redis_conn.publish(channel, message)
        await redis_gen.aclose()
    except Exception as exc:
        logger.warning(f"Redis publish failed ({channel}): {exc}")


async def tokenize(request: TokenizeRequest, identity_label: str, db: AsyncSession) -> AssetResponse:
    fabric = get_fabric()

    payload = await fabric.submit_transaction(
        "TokenizeAsset",
        request.asset_id,
        request.isin,
        request.asset_type,
        request.asset_name,
        request.issuer_lei,
        str(request.nominal_value),
        request.currency,
        request.issuance_date.isoformat(),
        request.justification,
        identity_label=identity_label,
    )

    if not isinstance(payload, dict):
        raise ValueError("Réponse invalide du chaincode lors de la tokenisation.")

    fabric_tx_id = str(payload.get("txID", ""))
    block_num_raw = payload.get("blockNumber")
    block_num = int(block_num_raw) if block_num_raw else None

    org_stmt = select(Organization).where(Organization.lei == request.issuer_lei)
    org_res = await db.execute(org_stmt)
    org = org_res.scalar_one_or_none()
    if not org:
        raise ValueError(f"Organisation introuvable pour le LEI: {request.issuer_lei}")

    user_stmt = select(User).where(User.org_id == org.id).limit(1)
    user_res = await db.execute(user_stmt)
    user = user_res.scalar_one_or_none()

    new_asset = Asset(
        asset_id=request.asset_id,
        isin=request.isin,
        asset_type=request.asset_type,
        asset_name=request.asset_name,
        issuer_org_id=org.id,
        current_owner_id=user.id if user else org.id,
        nominal_value=request.nominal_value,
        current_value=request.nominal_value,
        currency=request.currency,
        status="ACTIF",
        issuance_date=request.issuance_date,
        fabric_tx_id=fabric_tx_id,
        fabric_block_number=block_num,
    )
    db.add(new_asset)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await db.refresh(new_asset)

    await _publish_event("asset:events", f"TOKENIZE:{request.asset_id}")
    return AssetResponse.model_validate(new_asset)


async def transfer(
    request: TransferRequest,
    identity_label: str,
    db: AsyncSession,
    current_user: User | None = None,
) -> AssetResponse:
    stmt_asset = select(Asset).where(Asset.asset_id == request.asset_id)
    result_asset = await db.execute(stmt_asset)
    asset = result_asset.scalar_one_or_none()
    if asset is None:
        raise AssetNotFoundException(request.asset_id)

    if asset.status == "GELE":
        raise AssetFrozenError(asset.asset_id, "AMF-INV-2026-001")

    original_owner_id = asset.current_owner_id

    to_owner_res = await db.execute(select(User).where(User.email == request.to_owner).limit(1))
    to_owner_user = to_owner_res.scalar_one_or_none()
    if not to_owner_user:
        raise ValueError(f"Destinataire introuvable: {request.to_owner}")

    initiator_id = current_user.id if current_user else asset.current_owner_id

    is_blocked, reason, by = await full_check(
        participant_id=to_owner_user.id,
        amount=float(request.price),
        asset_id=request.asset_id,
        asset_type=asset.asset_type,
        counterparty_id=initiator_id,
        full_name=f"{to_owner_user.first_name or ''} {to_owner_user.last_name or ''}".strip() or to_owner_user.email,
        db=db,
    )
    if is_blocked:
        raise ComplianceBlockedError(reason=reason, blocked_by=by)

    fabric = get_fabric()
    payload = await fabric.submit_transaction(
        "TransferAsset",
        request.asset_id,
        request.to_owner,
        str(request.price),
        request.justification,
        identity_label=identity_label,
    )

    if not isinstance(payload, dict):
        raise ValueError("Réponse invalide du chaincode lors du transfert.")

    fabric_tx_id = str(payload.get("txID", ""))
    block_num = int(payload["blockNumber"]) if payload.get("blockNumber") else None
    previous_owner_email = current_user.email if current_user else None

    asset.current_owner_id = to_owner_user.id
    asset.current_value = request.price
    asset.fabric_tx_id = fabric_tx_id
    asset.fabric_block_number = block_num

    tx = Transaction(
        tx_ref=f"TX-{uuid.uuid4()}",
        fabric_tx_id=fabric_tx_id,
        fabric_block_number=block_num,
        tx_type="TRANSFERT",
        asset_id=asset.id,
        initiator_id=initiator_id,
        from_owner_id=original_owner_id,
        to_owner_id=to_owner_user.id,
        amount=request.price,
        settlement_date=asset.updated_at,
        regulatory_flag=False,
        justification=request.justification,
    )
    db.add(tx)
    try:
        await db.commit()
    except Exception as db_exc:
        logger.error(f"[SAGA] DB commit failed after Fabric TransferAsset. Compensating: {db_exc}")
        await db.rollback()
        if previous_owner_email:
            try:
                await fabric.submit_transaction(
                    "TransferAsset",
                    request.asset_id,
                    previous_owner_email,
                    str(request.price),
                    "SAGA_COMPENSATION: DB commit failure rollback",
                    identity_label=identity_label,
                )
                logger.info(f"[SAGA] Compensation successful for asset {request.asset_id}")
            except Exception as comp_exc:
                logger.critical(
                    f"[SAGA] CRITICAL: Compensation FAILED for asset {request.asset_id}. "
                    f"Manual intervention required. DB error: {db_exc}, comp error: {comp_exc}"
                )
        raise
    await db.refresh(asset)

    try:
        neo4j = get_neo4j_client()
        await neo4j.connect()
        await neo4j.ingest_transaction(
            tx_id=fabric_tx_id,
            asset_id=request.asset_id,
            from_actor=current_user.email if current_user else str(original_owner_id),
            to_actor=request.to_owner,
            amount=float(request.price),
            timestamp=asset.updated_at.isoformat() if asset.updated_at else "",
        )
    except Exception as exc:
        logger.warning(f"[GRAPH] Neo4j sync failed (non-blocking): {exc}")

    await _publish_event("asset:events", f"TRANSFER:{request.asset_id}")
    return AssetResponse.model_validate(asset)


async def freeze(
    request: FreezeRequest,
    identity_label: str,
    db: AsyncSession,
    current_user: User | None = None,
) -> AssetResponse:
    fabric = get_fabric()
    payload = await fabric.submit_transaction(
        "FreezeAsset",
        request.asset_id,
        request.reason,
        request.regulatory_ref,
        identity_label=identity_label,
    )

    if not isinstance(payload, dict):
        raise ValueError("Réponse invalide du chaincode lors du gel.")

    fabric_tx_id = str(payload.get("txID", ""))
    block_num = int(payload["blockNumber"]) if payload.get("blockNumber") else None

    result = await db.execute(select(Asset).where(Asset.asset_id == request.asset_id))
    asset = result.scalar_one_or_none()
    if asset is None:
        raise AssetNotFoundException(request.asset_id)
    initiator_id = current_user.id if current_user else asset.current_owner_id

    asset.status = "GELE"
    asset.fabric_tx_id = fabric_tx_id
    asset.fabric_block_number = block_num

    tx = Transaction(
        tx_ref=f"TX-{uuid.uuid4()}",
        fabric_tx_id=fabric_tx_id,
        fabric_block_number=block_num,
        tx_type="GEL",
        asset_id=asset.id,
        initiator_id=initiator_id,
        amount=asset.nominal_value,
        settlement_date=asset.updated_at,
        regulatory_flag=True,
        justification=request.reason,
    )
    db.add(tx)
    try:
        await db.commit()
    except Exception as db_exc:
        logger.error(f"[SAGA] DB commit failed after Fabric FreezeAsset. Compensating: {db_exc}")
        await db.rollback()
        try:
            await fabric.submit_transaction(
                "UnfreezeAsset",
                request.asset_id,
                "SAGA_COMPENSATION: DB commit failure rollback",
                identity_label=identity_label,
            )
            logger.info(f"[SAGA] Compensation UnfreezeAsset successful for asset {request.asset_id}")
        except Exception as comp_exc:
            logger.critical(
                f"[SAGA] CRITICAL: Compensation UnfreezeAsset FAILED for asset {request.asset_id}. "
                f"DB error: {db_exc}, comp error: {comp_exc}"
            )
        raise
    await db.refresh(asset)

    try:
        neo4j = get_neo4j_client()
        await neo4j.connect()
        await neo4j.ingest_freeze(
            asset_id=request.asset_id,
            actor=current_user.email if current_user else str(initiator_id),
            tx_id=fabric_tx_id,
        )
    except Exception as exc:
        logger.warning(f"[GRAPH] Neo4j freeze sync failed (non-blocking): {exc}")

    await _publish_event("asset:events", f"FREEZE:{request.asset_id}")
    return AssetResponse.model_validate(asset)


async def unfreeze_asset(
    request: UnfreezeRequest,
    identity_label: str,
    db: AsyncSession,
    current_user: User | None = None,
) -> AssetResponse:
    fabric = get_fabric()
    payload = await fabric.submit_transaction(
        "UnfreezeAsset",
        request.asset_id,
        request.justification,
        identity_label=identity_label,
    )

    if not isinstance(payload, dict):
        raise ValueError("Réponse invalide du chaincode lors du dégel.")

    fabric_tx_id = str(payload.get("txID", ""))
    block_num = int(payload["blockNumber"]) if payload.get("blockNumber") else None

    result = await db.execute(select(Asset).where(Asset.asset_id == request.asset_id))
    asset = result.scalar_one_or_none()
    if asset is None:
        raise AssetNotFoundException(request.asset_id)
    initiator_id = current_user.id if current_user else asset.current_owner_id

    asset.status = "ACTIF"
    asset.fabric_tx_id = fabric_tx_id
    asset.fabric_block_number = block_num

    tx = Transaction(
        tx_ref=f"TX-{uuid.uuid4()}",
        fabric_tx_id=fabric_tx_id,
        fabric_block_number=block_num,
        tx_type="DEGEL",
        asset_id=asset.id,
        initiator_id=initiator_id,
        amount=asset.nominal_value,
        settlement_date=asset.updated_at,
        regulatory_flag=True,
        justification=request.justification,
    )
    db.add(tx)
    try:
        await db.commit()
    except Exception as db_exc:
        logger.error(f"[SAGA] DB commit failed after Fabric UnfreezeAsset. Compensating: {db_exc}")
        await db.rollback()
        try:
            await fabric.submit_transaction(
                "FreezeAsset",
                request.asset_id,
                "SAGA_COMPENSATION: DB commit failure rollback",
                "SAGA-COMP",
                identity_label=identity_label,
            )
            logger.info(f"[SAGA] Compensation FreezeAsset successful for asset {request.asset_id}")
        except Exception as comp_exc:
            logger.critical(
                f"[SAGA] CRITICAL: Compensation FreezeAsset FAILED for asset {request.asset_id}. "
                f"DB error: {db_exc}, comp error: {comp_exc}"
            )
        raise
    await db.refresh(asset)

    await _publish_event("asset:events", f"UNFREEZE:{request.asset_id}")
    return AssetResponse.model_validate(asset)
