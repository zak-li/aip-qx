"""gRPC servicer for the Audit service."""
from __future__ import annotations

import json
import logging

import grpc
import grpc.aio
from celery.result import AsyncResult
from sqlalchemy import select

from backend.core.celery_app import celery_app
from backend.core.database import AsyncSessionLocal
from backend.dependencies import get_fabric, resolve_identity_from_payload
from backend.features.audit.tasks import generate_audit_report as task_generate
from backend.features.compliance.models import AuditLog
from backend.features.compliance.tasks import fraud_graph_scan
from backend.grpc_generated import audit_pb2, audit_pb2_grpc

logger = logging.getLogger(__name__)


class AuditServicer(audit_pb2_grpc.AuditServiceServicer):

    async def ListAuditLogs(
        self,
        request: audit_pb2.AuditListRequest,
        context: grpc.aio.ServicerContext,
    ) -> audit_pb2.AuditLogList:
        async with AsyncSessionLocal() as db:
            stmt = (
                select(AuditLog)
                .order_by(AuditLog.created_at.desc())
                .limit(request.limit or 50)
                .offset(request.offset or 0)
            )
            logs = (await db.execute(stmt)).scalars().all()

        entries = [
            audit_pb2.AuditLogEntry(
                id=str(log.id),
                user_id=str(log.user_id) if log.user_id else "",
                endpoint=log.endpoint or "",
                method=log.http_method or "",
                status_code=log.response_code or 0,
                duration_ms=log.duration_ms or 0,
                created_at=str(log.created_at) if log.created_at else "",
            )
            for log in logs
        ]
        return audit_pb2.AuditLogList(entries=entries)

    async def FetchAssetTrail(
        self,
        request: audit_pb2.AssetTrailRequest,
        context: grpc.aio.ServicerContext,
    ) -> audit_pb2.AssetTrailResponse:
        fabric = get_fabric()
        identity = resolve_identity_from_payload(context.user_payload)
        payload = await fabric.evaluate_transaction(
            "GetProvenanceTrail", request.asset_id, identity_label=identity
        )
        return audit_pb2.AssetTrailResponse(
            asset_id=request.asset_id,
            verified=True,
            blockchain_provenance=json.dumps(payload) if payload else "[]",
        )

    async def GenerateReport(
        self,
        request: audit_pb2.GenerateReportReq,
        context: grpc.aio.ServicerContext,
    ) -> audit_pb2.TaskResponse:
        user_id = context.user_payload["sub"]
        task = task_generate.delay(request.asset_id, user_id)
        return audit_pb2.TaskResponse(
            task_id=task.id,
            status="PENDING",
            message=f"Report generation for {request.asset_id} queued.",
        )

    async def GetReportStatus(
        self,
        request: audit_pb2.TaskIdRequest,
        context: grpc.aio.ServicerContext,
    ) -> audit_pb2.TaskStatusResponse:
        result = AsyncResult(request.task_id, app=celery_app)
        if result.state == "SUCCESS":
            return audit_pb2.TaskStatusResponse(
                task_id=request.task_id,
                status="SUCCESS",
                file_path=result.result.get("file_path", "") if result.result else "",
            )
        if result.state == "FAILURE":
            return audit_pb2.TaskStatusResponse(
                task_id=request.task_id,
                status="FAILURE",
                error=str(result.result),
            )
        return audit_pb2.TaskStatusResponse(task_id=request.task_id, status=result.state)

    async def TriggerFraudScan(
        self,
        request: audit_pb2.FraudScanRequest,
        context: grpc.aio.ServicerContext,
    ) -> audit_pb2.TaskResponse:
        task = fraud_graph_scan.delay()
        return audit_pb2.TaskResponse(
            task_id=task.id,
            status="PENDING",
            message="Neo4j fraud scan queued.",
        )
