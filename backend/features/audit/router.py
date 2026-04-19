from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi.responses import JSONResponse
from backend.dependencies import get_db, get_current_user, get_fabric, require_role, resolve_identity
from backend.features.auth.models import User
from backend.features.compliance.models import AuditLog
from backend.features.audit.tasks import generate_audit_report as task_generate

router = APIRouter()

@router.get("")
async def list_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, str | int | None]]:
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    logs = result.scalars().all()

    return [
        {
            "id": str(log.id),
            "user_id": str(log.user_id) if log.user_id else None,
            "endpoint": log.endpoint,
            "method": log.http_method,
            "status_code": log.response_code,
            "duration_ms": log.duration_ms,
            "created_at": str(log.created_at),
        }
        for log in logs
    ]

@router.get("/asset/{asset_id}")
async def fetch_audit_trail(
    asset_id: str,
    current_user: User = Depends(require_role("AUDITEUR", "REGULATEUR")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str | bool | list[dict[str, str | int | float | bool | None]] | None]:
    fabric = get_fabric()
    payload = await fabric.evaluate_transaction(
        "GetProvenanceTrail", asset_id, identity_label=resolve_identity(current_user)
    )

    return {"asset_id": asset_id, "verified": True, "blockchain_provenance": payload}

@router.post("/report/generate/{asset_id}", status_code=202)
async def generate_audit_report(
    asset_id: str,
    current_user: User = Depends(require_role("AUDITEUR")),
) -> JSONResponse:
    task = task_generate.delay(asset_id, str(current_user.id))
    return JSONResponse(
        status_code=202,
        content={
            "task_id": task.id,
            "status": "PENDING",
            "message": f"Génération du rapport pour {asset_id} en cours.",
        },
    )

@router.get("/report/status/{task_id}", status_code=200)
async def get_report_status(
    task_id: str,
    current_user: User = Depends(require_role("AUDITEUR")),
) -> dict[str, str]:
    from celery.result import AsyncResult
    from backend.core.celery_app import celery_app

    result = AsyncResult(task_id, app=celery_app)
    if result.state == "SUCCESS":
        return {"task_id": task_id, "status": "SUCCESS", "file_path": result.result.get("file_path", "")}
    if result.state == "FAILURE":
        return {"task_id": task_id, "status": "FAILURE", "error": str(result.result)}
    return {"task_id": task_id, "status": result.state}

@router.post("/fraud/scan", status_code=202)
async def trigger_fraud_scan(
    current_user: User = Depends(require_role("COMPLIANCE_OFFICER", "REGULATEUR", "SUPER_ADMIN")),
) -> dict[str, str]:
    from backend.features.compliance.tasks import fraud_graph_scan
    task = fraud_graph_scan.delay()
    return {
        "task_id": task.id,
        "status": "PENDING",
        "message": "Analyse fraude Neo4j lancée en arrière-plan.",
    }
