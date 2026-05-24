"""gRPC servicer for the Assets service."""
from __future__ import annotations

import grpc
import grpc.aio

from core.core.database import AsyncSessionLocal
from core.dependencies import get_fabric, resolve_identity_from_payload
from core.features.assets.schemas import (
    FreezeRequest as FreezeSchema,
)
from core.features.assets.schemas import (
    TokenizeRequest as TokenizeSchema,
)
from core.features.assets.schemas import (
    TransferRequest as TransferSchema,
)
from core.features.assets.schemas import (
    UnfreezeRequest as UnfreezeSchema,
)
from core.features.assets.service import freeze, tokenize, transfer, unfreeze_asset
from core.features.assets.valuation_service import get_history, record_valuation
from core.grpc_generated import assets_pb2, assets_pb2_grpc


class AssetsServicer(assets_pb2_grpc.AssetsServiceServicer):

    async def TokenizeAsset(
        self,
        request: assets_pb2.TokenizeRequest,
        context: grpc.aio.ServicerContext,
    ) -> assets_pb2.AssetResponse:
        async with AsyncSessionLocal() as db:
            schema = TokenizeSchema(
                asset_id=request.asset_id,
                asset_type=request.asset_type,
                isin=request.isin,
                lei=request.lei,
                currency=request.currency,
                face_value=request.face_value,
                owner=request.owner,
                metadata=request.metadata,
            )
            identity = resolve_identity_from_payload(context.user_payload)
            result = await tokenize(schema, identity, db)
        return _asset_to_proto(result)

    async def TransferAsset(
        self,
        request: assets_pb2.TransferRequest,
        context: grpc.aio.ServicerContext,
    ) -> assets_pb2.AssetResponse:
        async with AsyncSessionLocal() as db:
            schema = TransferSchema(
                asset_id=request.asset_id,
                new_owner=request.new_owner,
                amount=request.amount,
            )
            identity = resolve_identity_from_payload(context.user_payload)
            result = await transfer(schema, identity, db)
        return _asset_to_proto(result)

    async def FreezeAsset(
        self,
        request: assets_pb2.FreezeRequest,
        context: grpc.aio.ServicerContext,
    ) -> assets_pb2.AssetResponse:
        async with AsyncSessionLocal() as db:
            schema = FreezeSchema(asset_id=request.asset_id, reason=request.reason)
            identity = resolve_identity_from_payload(context.user_payload)
            result = await freeze(schema, identity, db)
        return _asset_to_proto(result)

    async def UnfreezeAsset(
        self,
        request: assets_pb2.UnfreezeRequest,
        context: grpc.aio.ServicerContext,
    ) -> assets_pb2.AssetResponse:
        async with AsyncSessionLocal() as db:
            schema = UnfreezeSchema(asset_id=request.asset_id, reason=request.reason)
            identity = resolve_identity_from_payload(context.user_payload)
            result = await unfreeze_asset(schema, identity, db)
        return _asset_to_proto(result)

    async def GetAsset(
        self,
        request: assets_pb2.AssetIdRequest,
        context: grpc.aio.ServicerContext,
    ) -> assets_pb2.AssetResponse:
        fabric = get_fabric()
        identity = resolve_identity_from_payload(context.user_payload)
        payload = await fabric.evaluate_transaction(
            "GetAsset", request.asset_id, identity_label=identity
        )
        if not isinstance(payload, dict):
            await context.abort(grpc.StatusCode.NOT_FOUND, "Asset not found")
        from core.features.assets.schemas import AssetResponse
        return _asset_to_proto(AssetResponse.model_validate(payload))

    async def GetAssetHistory(
        self,
        request: assets_pb2.AssetIdRequest,
        context: grpc.aio.ServicerContext,
    ) -> assets_pb2.ProvenanceResponse:
        fabric = get_fabric()
        identity = resolve_identity_from_payload(context.user_payload)
        payload = await fabric.evaluate_transaction(
            "GetProvenanceTrail", request.asset_id, identity_label=identity
        )
        if not isinstance(payload, list):
            return assets_pb2.ProvenanceResponse(records=[])
        records = [
            assets_pb2.ProvenanceRecord(
                tx_id=r.get("tx_id", ""),
                action=r.get("action", ""),
                actor=r.get("actor", ""),
                timestamp=str(r.get("timestamp", "")),
                metadata=str(r.get("metadata", "")),
            )
            for r in payload
        ]
        return assets_pb2.ProvenanceResponse(records=records)

    async def SearchAssets(
        self,
        request: assets_pb2.SearchRequest,
        context: grpc.aio.ServicerContext,
    ) -> assets_pb2.AssetList:
        import json
        fabric = get_fabric()
        identity = resolve_identity_from_payload(context.user_payload)
        query: dict = {"selector": {}}
        if request.status:
            query["selector"]["status"] = request.status
        if request.asset_type:
            query["selector"]["assetType"] = request.asset_type
        if request.owner:
            query["selector"]["owner"] = request.owner
        query["limit"] = request.limit or 10
        query["skip"] = request.offset or 0
        payload = await fabric.evaluate_transaction(
            "QueryAssets", json.dumps(query), identity_label=identity
        )
        if not isinstance(payload, list):
            return assets_pb2.AssetList(assets=[])
        from pydantic import TypeAdapter

        from core.features.assets.schemas import AssetResponse
        items = TypeAdapter(list[AssetResponse]).validate_python(payload)
        return assets_pb2.AssetList(assets=[_asset_to_proto(a) for a in items])

    async def ValuateAsset(
        self,
        request: assets_pb2.ValuateRequest,
        context: grpc.aio.ServicerContext,
    ) -> assets_pb2.ValuationResponse:
        async with AsyncSessionLocal() as db:
            try:
                valuation = await record_valuation(
                    db=db,
                    asset_id=request.asset_id,
                    current_value=request.current_value,
                    yield_to_maturity=request.yield_to_maturity,
                    duration=request.duration,
                    convexity=request.convexity,
                    credit_spread_bps=request.credit_spread_bps,
                    pricing_source=request.pricing_source,
                    valuation_date=request.valuation_date,
                )
            except ValueError as exc:
                await context.abort(grpc.StatusCode.NOT_FOUND, str(exc))
        return _valuation_to_proto(valuation)

    async def ListAssetValuations(
        self,
        request: assets_pb2.AssetIdRequest,
        context: grpc.aio.ServicerContext,
    ) -> assets_pb2.ValuationList:
        async with AsyncSessionLocal() as db:
            valuations = await get_history(db, request.asset_id)
        return assets_pb2.ValuationList(
            valuations=[_valuation_to_proto(v) for v in valuations]
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _asset_to_proto(a) -> assets_pb2.AssetResponse:
    return assets_pb2.AssetResponse(
        asset_id=str(a.asset_id or ""),
        asset_type=str(a.asset_type or ""),
        isin=str(a.isin or ""),
        lei=str(a.lei or ""),
        currency=str(a.currency or ""),
        face_value=float(a.face_value or 0),
        owner=str(a.owner or ""),
        status=str(a.status or ""),
        created_at=str(a.created_at or ""),
        updated_at=str(a.updated_at or ""),
    )


def _valuation_to_proto(v) -> assets_pb2.ValuationResponse:
    return assets_pb2.ValuationResponse(
        id=str(v.id or ""),
        asset_id=str(v.asset_id or ""),
        current_value=float(v.current_value or 0),
        yield_to_maturity=float(v.yield_to_maturity or 0),
        duration=float(v.duration or 0),
        convexity=float(v.convexity or 0),
        credit_spread_bps=int(v.credit_spread_bps or 0),
        pricing_source=str(v.pricing_source or ""),
        valuation_date=str(v.valuation_date or ""),
        created_at=str(v.created_at or ""),
    )
