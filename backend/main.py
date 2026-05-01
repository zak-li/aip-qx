import asyncio
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

import hvac
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from backend.api.middleware.auth_middleware import AuthMiddleware
from backend.api.middleware.rate_limiter import RateLimiterMiddleware
from backend.api.middleware.request_logger import RequestLoggerMiddleware
from backend.api.v1.router import api_router
from backend.config import settings
from backend.core.database import AsyncSessionLocal, engine
from backend.core.logging_config import setup_logging
from backend.core.redis_client import get_redis
from backend.dependencies import get_fabric
from backend.exceptions import setup_global_exception_handlers
from backend.fabric_client.events import FabricEventListener
from backend.features.agent.groq_client import close_client as close_groq_client
from backend.features.fraud_detection.neo4j_sync import get_neo4j_client

RWA_TRANSACTIONS = Counter("rwa_transactions_total", "Transactions RWA", ["tx_type", "org", "status"])
RWA_CHAINCODE_DURATION = Histogram(
    "rwa_chaincode_duration_seconds", "Duree chaincode",
    ["function", "status"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1, 2, 3, 5, 10],
)
RWA_ASSETS_BY_STATUS = Gauge("rwa_assets_by_status", "Actifs par statut", ["status"])
RWA_KYC_EXPIRING = Gauge("rwa_kyc_expiring_count", "KYC expirant")
RWA_AML_SCORE = Gauge("rwa_aml_score_avg", "AML score", ["risk_category"])
RWA_COMPLIANCE_BLOCKS = Counter("rwa_compliance_blocks_total", "Compliance Blocks", ["blocked_by"])
RWA_CELERY_TASKS = Counter("rwa_celery_tasks_total", "Taches Celery", ["task_name", "status"])

# Initialise label combinations so they appear in /metrics from startup.
# Circuit-breaker state is declared and labelled in backend/core/circuit_breaker.py
# (and the legacy fabric_client retry decorator), so we no longer touch it here.
RWA_COMPLIANCE_BLOCKS.labels(blocked_by="aml_screening").inc(0)
RWA_COMPLIANCE_BLOCKS.labels(blocked_by="kyc_expired").inc(0)
RWA_CELERY_TASKS.labels(task_name="generate_audit_report", status="success").inc(0)
RWA_CELERY_TASKS.labels(task_name="generate_audit_report", status="failure").inc(0)
RWA_CELERY_TASKS.labels(task_name="sync_fabric_events", status="success").inc(0)

setup_logging(settings.log_level)
logger = logging.getLogger(__name__)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=(), payment=()",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    ),
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers[name] = value
        return response


async def metrics_updater() -> None:
    while True:
        try:
            async with AsyncSessionLocal() as db:
                for row_status, cnt in await db.execute(text("SELECT status, COUNT(*) FROM assets GROUP BY status")):
                    if row_status:
                        RWA_ASSETS_BY_STATUS.labels(status=row_status).set(cnt)

                res_kyc = await db.execute(
                    text("SELECT COUNT(*) FROM compliance_records WHERE expires_at BETWEEN now() AND now() + interval '30 days'")
                )
                RWA_KYC_EXPIRING.set(res_kyc.scalar() or 0)

                for cat, avg_val in await db.execute(
                    text("SELECT risk_category, AVG(aml_score) FROM compliance_records GROUP BY risk_category")
                ):
                    if cat and avg_val is not None:
                        RWA_AML_SCORE.labels(risk_category=cat).set(float(avg_val))
        except Exception as exc:
            logger.error(f"Metrics update error: {exc}")
        await asyncio.sleep(60)


_event_listener_instance: FabricEventListener | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting up RWA API.")

    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("PostgreSQL connection verified.")
    except Exception as exc:
        logger.error(f"PostgreSQL connection failed: {exc}")

    try:
        redis_conn = await anext(get_redis())
        await redis_conn.ping()
        logger.info("Redis connection verified.")
    except Exception as exc:
        logger.error(f"Redis connection failed: {exc}")

    try:
        await get_fabric().connect()
        logger.info("Hyperledger Fabric gRPC channel connected.")
    except Exception as exc:
        logger.error(f"Fabric connection failed: {exc}")

    neo4j_client = get_neo4j_client()
    try:
        await neo4j_client.connect()
        logger.info("Neo4j graph database connected.")
    except Exception as exc:
        logger.warning(f"Neo4j connection failed (non-blocking): {exc}")

    global _event_listener_instance
    _event_listener_instance = FabricEventListener(settings)
    try:
        await _event_listener_instance.start()
        logger.info("Fabric event listener started.")
    except Exception as exc:
        logger.error(f"Fabric event listener failed to start: {exc}")

    metrics_task = asyncio.create_task(metrics_updater(), name="metrics_updater")

    try:
        yield
    finally:
        logger.info("Shutting down RWA API.")
        metrics_task.cancel()

        if _event_listener_instance:
            try:
                await _event_listener_instance.stop()
            except Exception:
                logger.exception("Event listener failed to stop cleanly")

        for cleanup in (
            get_fabric().disconnect,
            engine.dispose,
            neo4j_client.close,
            close_groq_client,
        ):
            try:
                await cleanup()
            except Exception:
                logger.exception("Shutdown cleanup step failed")


_is_prod = settings.environment == "production"
app = FastAPI(
    title="RWA Tokenization Backend",
    version="1.4.0",
    lifespan=lifespan,
    docs_url=None if _is_prod else "/docs",
    redoc_url=None if _is_prod else "/redoc",
    openapi_url=None if _is_prod else "/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.allowed_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(AuthMiddleware)
app.add_middleware(RateLimiterMiddleware)
app.add_middleware(RequestLoggerMiddleware)

Instrumentator().instrument(app)
setup_global_exception_handlers(app)
app.include_router(api_router, prefix="/api/v1")


@app.exception_handler(Exception)
async def global_unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("UNHANDLED EXCEPTION IN API")
    return JSONResponse(
        status_code=500,
        content={"error": "InternalServerError", "message": "An internal error occurred."},
    )


@app.get("/health", tags=["System"])
async def check_health() -> JSONResponse:
    """Public liveness probe — only returns ok/degraded, no subsystem details."""
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
    except Exception:
        logger.exception("health: postgres check failed")
        return JSONResponse(status_code=503, content={"status": "degraded"})
    return JSONResponse(status_code=200, content={"status": "healthy"})


def _is_trusted_internal(client_ip: str) -> bool:
    return client_ip.startswith("127.") or client_ip.startswith("10.10.10.")


@app.get("/health/deep", tags=["System"], include_in_schema=False)
async def check_health_deep(request: Request) -> JSONResponse:
    """Detailed health check — restricted to trusted internal IPs only."""
    client_ip = request.client.host if request.client else "unknown"
    if not _is_trusted_internal(client_ip):
        return JSONResponse(status_code=403, content={"error": "Forbidden"})

    checks: dict[str, str] = {}
    overall_ok = True

    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception:
        logger.exception("health: postgres check failed")
        checks["postgres"] = "error"
        overall_ok = False

    try:
        redis_conn = await anext(get_redis())
        await redis_conn.ping()
        checks["redis"] = "ok"
    except Exception:
        logger.exception("health: redis check failed")
        checks["redis"] = "error"
        overall_ok = False

    try:
        await get_fabric().connect()
        checks["fabric"] = "ok"
    except Exception:
        logger.exception("health: fabric check failed")
        checks["fabric"] = "error"
        overall_ok = False

    try:
        neo4j = get_neo4j_client()
        if neo4j._driver is not None:
            await neo4j._driver.verify_connectivity()
            checks["neo4j"] = "ok"
        else:
            checks["neo4j"] = "disconnected"
    except Exception:
        logger.exception("health: neo4j check failed")
        checks["neo4j"] = "error"

    try:
        vault_client = hvac.Client(url=settings.vault_addr, token=settings.vault_token)
        checks["vault"] = "ok" if vault_client.is_authenticated() else "unauthenticated"
    except Exception:
        logger.exception("health: vault check failed")
        checks["vault"] = "error"

    return JSONResponse(
        status_code=200 if overall_ok else 503,
        content={"status": "healthy" if overall_ok else "degraded", "checks": checks},
    )


@app.get("/metrics", include_in_schema=False)
async def get_metrics(request: Request) -> Response:
    client_ip = request.client.host if request.client else "unknown"
    if not _is_trusted_internal(client_ip):
        return JSONResponse(status_code=403, content={"error": "Forbidden"})
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
