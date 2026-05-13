import json
import os
from datetime import UTC, datetime

from celery import Task
from sqlalchemy import text

from backend.core.celery_app import celery_app
from backend.core.celery_async import run_async
from backend.core.database import AsyncSessionLocal
from backend.dependencies import get_fabric
from backend.features.audit.integrity_checker import IntegrityChecker
from backend.features.audit.report_generator import ReportGenerator
from backend.features.audit.trail import AuditTrail


async def _do_generate_audit(asset_id: str, requested_by_id: str) -> dict:
    fabric = get_fabric()
    await fabric.connect()
    trail = AuditTrail(fabric_client=fabric, identity_label="admin@bank01")

    provenance = await trail.get_provenance(asset_id)
    raw_state = await trail.get_asset_state(asset_id)

    checker = IntegrityChecker()
    report = checker.check(asset_id, provenance)

    gen = ReportGenerator()
    pdf_bytes = await gen.generate(asset_id, raw_state, provenance, report, generated_by=requested_by_id)

    out_dir = "/tmp/rwa-reports"  # noqa: S108  # nosec B108
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    path = os.path.join(out_dir, f"{asset_id}_{ts}.pdf")

    with open(path, "wb") as f:  # noqa: ASYNC230
        f.write(pdf_bytes)

    async with AsyncSessionLocal() as session:
        pay = {
            "asset_id": asset_id,
            "file_path": path,
            "integrity_valid": report.valid,
            "generated_by": requested_by_id,
        }
        istmt = text("""
            INSERT INTO network_events
                (event_name, chaincode_name, fabric_tx_id, fabric_block_number, payload)
            VALUES
                (:name, :cc, :tx, :block, :pay)
        """)
        await session.execute(istmt, {
            "name": "AUDIT_REPORT_READY",
            "cc": "rwa-token",
            "tx": "N/A",
            "block": 0,
            "pay": json.dumps(pay),
        })
        await session.commit()

    return {
        "asset_id": asset_id,
        "file_path": path,
        "integrity_valid": report.valid,
        "pages": 0,
    }

@celery_app.task(queue="reports", bind=True, max_retries=2)
def generate_audit_report(self: Task, asset_id: str, requested_by_id: str) -> dict:
    return run_async(_do_generate_audit(asset_id, requested_by_id))

async def _do_generate_portfolio(org_id: str) -> dict:
    async with AsyncSessionLocal() as session:
        stmt = text("""
            SELECT asset_id, asset_name, asset_type, current_value
            FROM assets
            WHERE issuer_org_id = :org_id::uuid AND status != 'REMBOURSE'
        """)
        res = await session.execute(stmt, {"org_id": org_id})
        rows = res.fetchall()

        count = len(rows)
        total = sum(float(r[3]) if len(r) > 3 and r[3] is not None else 0.0 for r in rows)

        out_dir = "/tmp/rwa-reports"  # noqa: S108  # nosec B108
        os.makedirs(out_dir, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        path = os.path.join(out_dir, f"PORTFOLIO_{org_id[:8]}_{ts}.pdf")

        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate

        doc = SimpleDocTemplate(path, pagesize=A4)
        styles = getSampleStyleSheet()
        elements = [
            Paragraph(f"Portefeuille (Org: {org_id})", styles["Heading1"]),
            Paragraph(f"Actifs: {count} | Total: {total:,.2f} EUR", styles["Normal"]),
        ]
        doc.build(elements)

    return {"org_id": org_id, "file_path": path, "asset_count": count, "total_value_eur": float(total)}

@celery_app.task(queue="reports", bind=True, max_retries=2)
def generate_portfolio_report(self: Task, org_id: str) -> dict:
    return run_async(_do_generate_portfolio(org_id))
