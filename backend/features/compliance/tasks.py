import json
import logging

from sqlalchemy import text

from backend.core.audit_helpers import log_task_audit
from backend.core.celery_app import celery_app
from backend.core.celery_async import run_async
from backend.core.database import AsyncSessionLocal
from backend.features.compliance.aml import AMLScorer
from backend.features.compliance.sar_reporter import SARReporter
from backend.features.fraud_detection.neo4j_sync import get_neo4j_client

logger = logging.getLogger(__name__)

async def _do_kyc_expiry() -> dict:
    async with AsyncSessionLocal() as session:
        q = text("""
            SELECT u.id, u.email, c.expires_at
            FROM users u
            JOIN compliance_records c ON c.participant_id = u.id
            WHERE c.expires_at BETWEEN now() AND now() + interval '30 days'
        """)
        res = await session.execute(q)
        rows = res.fetchall()

        warnings_count = 0
        now_dt = await session.execute(text("SELECT now()"))
        current_time = now_dt.scalar()

        for r in rows:
            uid, email, exp = r
            days_rem = (exp - current_time).days if current_time and exp else 0

            pay = {
                "user_id": str(uid),
                "email": email,
                "expires_at": exp.isoformat() if exp else None,
                "days_remaining": days_rem,
            }
            istmt = text("""
                INSERT INTO network_events
                    (event_name, chaincode_name, fabric_tx_id, fabric_block_number, payload)
                VALUES
                    (:name, :cc, :tx, :block, :pay)
            """)
            await session.execute(istmt, {
                "name": "KYC_EXPIRY_WARNING",
                "cc": "rwa-token",
                "tx": "N/A",
                "block": 0,
                "pay": json.dumps(pay),
            })
            warnings_count += 1

        await session.commit()
        ret = {"checked": len(rows), "warnings": warnings_count}
        await log_task_audit("check_kyc_expiry", ret)
        return ret

@celery_app.task(queue="compliance")
def check_kyc_expiry() -> dict:
    return run_async(_do_kyc_expiry())

async def _do_aml_screening() -> dict:
    from uuid import UUID

    from backend.config import settings as _settings

    async with AsyncSessionLocal() as session:
        q = text("""
            SELECT DISTINCT initiator_id
            FROM transactions
            WHERE created_at > now() - interval '7 days'
            AND initiator_id IS NOT NULL
        """)
        res = await session.execute(q)
        users = res.scalars().all()

        screened = 0
        sar_gen = 0

        scorer = AMLScorer(_settings, session)

        for uid in users:
            screened += 1
            try:
                uid_obj = UUID(str(uid))
                from uuid import UUID as _UUID
                aml_result = await scorer.score(uid_obj, 0.0, _UUID(int=0))
                if aml_result.sar_required:
                    sar_gen += 1
                    generate_sar.delay(
                        str(uid), None,
                        "EXCEED_THRESHOLD",
                        0.0,
                        "AML-AUTO",
                    )
            except Exception as exc:
                logger.warning(f"AML scoring failed for {uid}: {exc}")

        await session.commit()

    ret = {"screened": screened, "updated": len(users), "sar_generated": sar_gen}
    await log_task_audit("run_periodic_aml_screening", ret)
    return ret

@celery_app.task(queue="compliance")
def run_periodic_aml_screening() -> dict:
    return run_async(_do_aml_screening())

async def _do_generate_sar(participant_id: str, tx_id: str | None, reason_code: str, amount: float, regulatory_ref: str | None) -> str:
    from uuid import UUID

    from backend.config import settings as _settings

    async with AsyncSessionLocal() as session:
        reporter = SARReporter(_settings, session)
        ref = await reporter.generate(
            participant_id=UUID(participant_id),
            tx_id=UUID(tx_id) if tx_id else None,
            reason_code=reason_code,
            amount=amount,
            regulatory_ref=regulatory_ref,
        )

    await log_task_audit("generate_sar", {"ref": ref, "participant_id": participant_id})
    return ref

@celery_app.task(queue="compliance")
def generate_sar(participant_id: str, tx_id: str | None, reason_code: str, amount: float, regulatory_ref: str | None) -> str:
    return run_async(_do_generate_sar(participant_id, tx_id, reason_code, amount, regulatory_ref))

async def _do_fraud_graph_scan() -> dict:
    client = get_neo4j_client()
    await client.connect()
    try:
        results = await client.run_fraud_scan()
        total = sum(len(v) for v in results.values())
        await log_task_audit("fraud_graph_scan", {"total_anomalies": total, **{k: len(v) for k, v in results.items()}})
        return {"total_anomalies": total, **{k: len(v) for k, v in results.items()}}
    finally:
        await client.close()

@celery_app.task(queue="compliance")
def fraud_graph_scan() -> dict:
    return run_async(_do_fraud_graph_scan())
