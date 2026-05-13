import json

from celery import Task
from sqlalchemy import text

from backend.core.celery_app import celery_app
from backend.core.celery_async import CELERY_AUDIT_IP, run_async
from backend.core.database import AsyncSessionLocal
from backend.core.redis_client import get_redis
from backend.dependencies import get_fabric

_SYNCABLE_COLUMNS = frozenset({"current_value", "status", "current_owner_id"})


async def _log_audit_result(task_name: str, payload: dict) -> None:
    async with AsyncSessionLocal() as session:
        stmt = text("""
            INSERT INTO audit_logs
                (endpoint, http_method, ip_address, response_code, duration_ms, request_body)
            VALUES (:endpoint, 'CELERY', :ip, 200, 0, :body::jsonb)
        """)
        await session.execute(
            stmt,
            {"endpoint": task_name, "ip": CELERY_AUDIT_IP, "body": json.dumps(payload)},
        )
        await session.commit()

async def _do_sync_fabric_state(asset_id: str) -> dict:
    client = get_fabric()
    raw_state = await client.evaluate_transaction("GetAsset", asset_id, identity_label="admin@bank01")
    if not isinstance(raw_state, dict):
        return {"asset_id": asset_id, "synced": False, "changes": []}

    async with AsyncSessionLocal() as session:
        stmt = text("SELECT current_value, status, current_owner_id FROM assets WHERE asset_id = :aid")
        res = await session.execute(stmt, {"aid": asset_id})
        row = res.fetchone()
        if not row:
            return {"asset_id": asset_id, "synced": False, "changes": ["Not found in DB"]}

        changes = []
        db_val, db_status, db_owner = row
        f_val = float(raw_state.get("nominal_value", 0)) if "nominal_value" in raw_state else None
        if "current_value" in raw_state:
            f_val = float(raw_state["current_value"])

        f_status = raw_state.get("status")
        f_owner = raw_state.get("current_owner_id")

        upd = {}
        if f_val is not None and abs(float(db_val) - f_val) > 0.001:
            upd["current_value"] = f_val
            changes.append("current_value")
        if f_status and db_status != f_status:
            upd["status"] = f_status
            changes.append("status")
        if f_owner and str(db_owner) != f_owner:
            upd["current_owner_id"] = f_owner
            changes.append("current_owner_id")

        if upd:
            invalid = set(upd) - _SYNCABLE_COLUMNS
            if invalid:
                raise ValueError(f"Refusing to sync unknown columns: {invalid}")
            sets = ", ".join([f"{k} = :{k}" for k in upd])
            upd["aid"] = asset_id
            ustmt = text(f"UPDATE assets SET {sets} WHERE asset_id = :aid")  # noqa: S608  # nosec B608
            await session.execute(ustmt, upd)
            await session.commit()

    res = {"asset_id": asset_id, "synced": True, "changes": changes}
    await _log_audit_result("sync_fabric_state", res)
    return res

@celery_app.task(bind=True, queue="fabric_events", max_retries=3, default_retry_delay=60)
def sync_fabric_state(self: Task, asset_id: str) -> dict:
    return run_async(_do_sync_fabric_state(asset_id))

_SYNC_BATCH_SIZE = 500


async def _do_sync_all() -> dict:
    launched = 0
    async with AsyncSessionLocal() as session:
        offset = 0
        while True:
            stmt = text(
                "SELECT DISTINCT asset_id FROM assets "
                "WHERE status != 'REMBOURSE' "
                "ORDER BY asset_id "
                "LIMIT :limit OFFSET :offset"
            )
            res = await session.execute(stmt, {"limit": _SYNC_BATCH_SIZE, "offset": offset})
            batch = res.scalars().all()
            if not batch:
                break
            for a_id in batch:
                sync_fabric_state.delay(a_id)
            launched += len(batch)
            offset += _SYNC_BATCH_SIZE
            if len(batch) < _SYNC_BATCH_SIZE:
                break
    res_payload = {"launched": launched}
    await _log_audit_result("sync_fabric_state_all", res_payload)
    return res_payload

@celery_app.task(queue="fabric_events")
def sync_fabric_state_all() -> dict:
    return run_async(_do_sync_all())

async def _do_process_event(event_type: str, payload: dict) -> None:
    async with AsyncSessionLocal() as session:
        istmt = text("""
            INSERT INTO network_events (event_type, payload, created_at)
            VALUES (:et, :pay, now())
        """)
        await session.execute(istmt, {"et": event_type, "pay": json.dumps(payload)})

        aid = payload.get("asset_id")
        if aid:
            if event_type == "AssetTransferred":
                val = payload.get("price", payload.get("amount", 0))
                own = payload.get("to_owner")
                if own:
                    await session.execute(
                        text("UPDATE assets SET current_value = :v, current_owner_id = :o WHERE asset_id = :a"),
                        {"v": val, "o": own, "a": aid}
                    )
            elif event_type == "AssetFrozen":
                await session.execute(
                    text("UPDATE assets SET status = 'GELE', regulatory_flag = True WHERE asset_id = :a"),
                    {"a": aid}
                )
            elif event_type == "AssetUnfrozen":
                await session.execute(
                    text("UPDATE assets SET status = 'ACTIF' WHERE asset_id = :a"),
                    {"a": aid}
                )
        await session.commit()

@celery_app.task(queue="fabric_events")
def process_fabric_event(event_type: str, payload: dict) -> None:
    run_async(_do_process_event(event_type, payload))

async def _do_update_cache(asset_id: str) -> None:
    async for redis_conn in get_redis():
        await redis_conn.delete(f"asset:{asset_id}")
        break

@celery_app.task(queue="fabric_events")
def update_asset_cache(asset_id: str) -> None:
    run_async(_do_update_cache(asset_id))
