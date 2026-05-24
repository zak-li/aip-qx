import logging

from sqlalchemy import text

from core.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


async def log_task_audit(task_name: str, payload: dict) -> None:
    """Insert a Celery task completion record into audit_logs.

    Background tasks have no client IP — we record `internal` as a sentinel
    so the column never carries a misleading value.
    """
    try:
        async with AsyncSessionLocal() as session:
            stmt = text("""
                INSERT INTO audit_logs
                    (endpoint, http_method, ip_address, response_code, duration_ms)
                VALUES
                    (:endpoint, :method, :ip, :code, :duration)
            """)
            await session.execute(stmt, {
                "endpoint": f"/tasks/{task_name}",
                "method": "CELERY",
                "ip": "internal",
                "code": 200,
                "duration": 0,
            })
            await session.commit()
    except Exception as exc:
        logger.warning(f"Failed to write task audit log for {task_name}: {exc}")
