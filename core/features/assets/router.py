import json
from collections.abc import Mapping

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from core.dependencies import get_current_user, get_db, get_fabric, require_role, resolve_identity
from core.features.assets.schemas import (
    AssetResponse,
    FreezeRequest,
    ProvenanceRecord,
    TokenizeRequest,
    TransferRequest,
    UnfreezeRequest,
    ValuateRequest,
    ValuationResponse,
)
from core.features.assets.service import freeze, tokenize, transfer, unfreeze_asset
from core.features.assets.valuation_service import get_history, record_valuation
from core.features.auth.models import User

router = APIRouter()


@router.post("/tokenize", response_model=AssetResponse, status_code=status.HTTP_201_CREATED)
async def create_asset(
    request: TokenizeRequest,
    current_user: User = Depends(require_role("EMETTEUR", "SUPER_ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> AssetResponse:
    return await tokenize(request, resolve_identity(current_user), db)


@router.post("/transfer", response_model=AssetResponse)
async def transfer_asset(
    request: TransferRequest,
    current_user: User = Depends(require_role("EMETTEUR", "TRADER", "CUSTODIAN")),
    db: AsyncSession = Depends(get_db),
) -> AssetResponse:
    return await transfer(request, resolve_identity(current_user), db, current_user=current_user)


@router.post("/freeze", response_model=AssetResponse)
async def freeze_asset(
    request: FreezeRequest,
    current_user: User = Depends(require_role("REGULATEUR", "SUPER_ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> AssetResponse:
    return await freeze(request, resolve_identity(current_user), db, current_user=current_user)


@router.post("/unfreeze", response_model=AssetResponse)
async def unfreeze_asset_endpoint(
    request: UnfreezeRequest,
    current_user: User = Depends(require_role("REGULATEUR", "SUPER_ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> AssetResponse:
    return await unfreeze_asset(request, resolve_identity(current_user), db, current_user=current_user)


@router.get("/{asset_id}", response_model=AssetResponse)
async def read_asset(
    asset_id: str,
    current_user: User = Depends(get_current_user),
) -> AssetResponse:
    fabric = get_fabric()
    payload = await fabric.evaluate_transaction(
        "GetAsset", asset_id, identity_label=resolve_identity(current_user)
    )
    if not isinstance(payload, dict):
        raise ValueError("Réponse invalide du chaincode lors de la lecture de l'actif.")
    return AssetResponse.model_validate(payload)


@router.get("/{asset_id}/history", response_model=list[ProvenanceRecord])
async def read_asset_history(
    asset_id: str,
    current_user: User = Depends(get_current_user),
) -> list[ProvenanceRecord]:
    fabric = get_fabric()
    payload = await fabric.evaluate_transaction(
        "GetProvenanceTrail", asset_id, identity_label=resolve_identity(current_user)
    )
    if not isinstance(payload, list):
        raise ValueError("Réponse invalide du chaincode lors de la lecture de la provenance.")
    adapter = TypeAdapter(list[ProvenanceRecord])
    return adapter.validate_python(payload)


@router.post("/{asset_id}/valuate", response_model=ValuationResponse, status_code=201)
async def valuate_asset(
    asset_id: str,
    body: ValuateRequest,
    current_user: User = Depends(require_role("COMPLIANCE_OFFICER", "SUPER_ADMIN", "EMETTEUR")),
    db: AsyncSession = Depends(get_db),
) -> ValuationResponse:
    try:
        valuation = await record_valuation(
            db=db,
            asset_id=asset_id,
            current_value=body.current_value,
            yield_to_maturity=body.yield_to_maturity,
            duration=body.duration,
            convexity=body.convexity,
            credit_spread_bps=body.credit_spread_bps,
            pricing_source=body.pricing_source,
            valuation_date=body.valuation_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ValuationResponse.model_validate(valuation)


@router.get("/{asset_id}/valuations", response_model=list[ValuationResponse])
async def list_asset_valuations(
    asset_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ValuationResponse]:
    valuations = await get_history(db, asset_id)
    return [ValuationResponse.model_validate(v) for v in valuations]


@router.get("", response_model=list[AssetResponse])
async def search_assets(
    asset_status: str | None = Query(None, alias="status"),
    asset_type: str | None = None,
    owner: str | None = None,
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
) -> list[AssetResponse]:
    fabric = get_fabric()

    query: dict[str, Mapping[str, str | dict[str, str]]] = {"selector": {}}
    if asset_status:
        query["selector"]["status"] = asset_status
    if asset_type:
        query["selector"]["assetType"] = asset_type
    if owner:
        query["selector"]["owner"] = owner

    query["limit"] = limit
    query["skip"] = offset

    payload = await fabric.evaluate_transaction(
        "QueryAssets", json.dumps(query), identity_label=resolve_identity(current_user)
    )

    if not isinstance(payload, list):
        return []

    adapter = TypeAdapter(list[AssetResponse])
    return adapter.validate_python(payload)
