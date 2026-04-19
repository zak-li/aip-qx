import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from typing import Awaitable, Callable

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
from backend.features.fraud_detection.neo4j_sync import get_neo4j_client

RWA_TRANSACTIONS = Counter("rwa_transactions_total", "Transactions RWA", ["tx_type", "org", "status"])
RWA_CHAINCODE_DURATION = Histogram("rwa_chaincode_duration_seconds", "Duree chaincode", ["function", "status"], buckets=[0.05, 0.1, 0.25, 0.5, 1, 2, 3, 5, 10])
RWA_ASSETS_BY_STATUS = Gauge("rwa_assets_by_status", "Actifs par statut", ["status"])
RWA_KYC_EXPIRING = Gauge("rwa_kyc_expiring_count", "KYC expirant")
RWA_AML_SCORE = Gauge("rwa_aml_score_avg", "AML score", ["risk_category"])
RWA_COMPLIANCE_BLOCKS = Counter("rwa_compliance_blocks_total", "Compliance Blocks", ["blocked_by"])
RWA_CIRCUIT_BREAKER = Gauge("rwa_circuit_breaker_state", "Circuit breaker", ["component"])
RWA_CELERY_TASKS = Counter("rwa_celery_tasks_total", "Taches Celery", ["task_name", "status"])

RWA_CIRCUIT_BREAKER.labels(component="fabric_gateway").set(0)
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
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin",
}

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        for header_name, header_value in SECURITY_HEADERS.items():
            response.headers[header_name] = header_value
        return response

async def metrics_updater() -> None:
    while True:
        try:
            async with AsyncSessionLocal() as db:
                res_status = await db.execute(text("SELECT status, COUNT(*) FROM assets GROUP BY status"))
                for row_status, cnt in res_status:
                    if row_status:
                        RWA_ASSETS_BY_STATUS.labels(status=row_status).set(cnt)

                res_kyc = await db.execute(text("SELECT COUNT(*) FROM compliance_records WHERE expires_at BETWEEN now() AND now() + interval '30 days'"))
                RWA_KYC_EXPIRING.set(res_kyc.scalar() or 0)

                res_aml = await db.execute(text("SELECT risk_category, AVG(aml_score) FROM compliance_records GROUP BY risk_category"))
                for cat, avg_val in res_aml:
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
        redis_gen = get_redis()
        redis_conn = await redis_gen.__anext__()
        await redis_conn.ping()
        await redis_gen.aclose()
        logger.info("Redis connection verified.")
    except Exception as exc:
        logger.error(f"Redis connection failed: {exc}")

    fabric_client = get_fabric()
    try:
        await fabric_client.connect()
        logger.info("Hyperledger Fabric gRPC channel connected.")
    except Exception as exc:
        logger.error(f"Fabric connection failed: {exc}")

    # Neo4j connection (best-effort — fraud detection degrades gracefully)
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
        logger.info("Event listener tracking context systematically deployed.")
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
                pass

        try:
            await fabric_client.disconnect()
        except Exception:
            pass

        try:
            await engine.dispose()
        except Exception:
            pass

        try:
            await neo4j_client.close()
        except Exception:
            pass

app = FastAPI(
    title="RWA Tokenization Backend",
    version="1.4.0",
    lifespan=lifespan,
)

domains = [origin.strip() for origin in settings.allowed_origins.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=domains,
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

# ── Serve Vite SPA (frontend/dist/) ──────────────────────────────────────────
import os as _os
_dist = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", "frontend", "dist"))

# Hashed JS/CSS chunks
app.mount("/assets", StaticFiles(directory=_os.path.join(_dist, "assets")), name="spa-assets")

# Lottie animations and other public files
app.mount("/animations", StaticFiles(directory=_os.path.join(_dist, "animations")), name="spa-animations")

@app.get("/favicon.svg",      include_in_schema=False)
async def _favicon():      return FileResponse(_os.path.join(_dist, "favicon.svg"))

@app.get("/robots.txt",       include_in_schema=False)
async def _robots():       return FileResponse(_os.path.join(_dist, "robots.txt"))

@app.get("/site.webmanifest", include_in_schema=False)
async def _manifest():     return FileResponse(_os.path.join(_dist, "site.webmanifest"))

@app.exception_handler(Exception)
async def global_unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("UNHANDLED EXCEPTION IN API")
    return JSONResponse(
        status_code=500,
        content={"error": "InternalServerError", "message": f"CRASH: {str(exc)}"},
    )

@app.get("/health", tags=["System"])
async def check_health() -> dict:
    """Deep health check — verifies connectivity to all subsystems."""
    checks: dict[str, str] = {}
    overall_ok = True

    # PostgreSQL
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:
        checks["postgres"] = f"error: {exc}"
        overall_ok = False

    # Redis
    try:
        redis_gen = get_redis()
        redis_conn = await redis_gen.__anext__()
        await redis_conn.ping()
        await redis_gen.aclose()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"
        overall_ok = False

    # Fabric (lightweight evaluate — no chaincode invoke)
    try:
        fabric_client = get_fabric()
        await fabric_client.connect()
        checks["fabric"] = "ok"
    except Exception as exc:
        checks["fabric"] = f"error: {exc}"
        overall_ok = False

    # Neo4j
    try:
        neo4j = get_neo4j_client()
        if neo4j._driver is not None:
            await neo4j._driver.verify_connectivity()
            checks["neo4j"] = "ok"
        else:
            checks["neo4j"] = "disconnected"
    except Exception as exc:
        checks["neo4j"] = f"error: {exc}"

    # Vault
    try:
        import hvac
        vault = hvac.Client(url=settings.vault_addr, token=settings.vault_token)
        checks["vault"] = "ok" if vault.is_authenticated() else "unauthenticated"
    except Exception as exc:
        checks["vault"] = f"error: {exc}"

    status_code = 200 if overall_ok else 503
    return JSONResponse(
        status_code=status_code,
        content={"status": "healthy" if overall_ok else "degraded", "checks": checks},
    )

@app.get("/metrics", include_in_schema=False)
async def metrics(request: Request) -> Response:
    client_ip = request.client.host if request.client else "unknown"
    if not (client_ip.startswith("127.") or client_ip.startswith("10.10.10.")):
        return JSONResponse(status_code=403, content={"error": "Forbidden", "message": "Accès refusé."})
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

# SPA catch-all — must be last so all API/health/metrics routes take priority
@app.get("/{full_path:path}", include_in_schema=False)
async def serve_spa(full_path: str):
    return FileResponse(
        _os.path.join(_dist, "index.html"),
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )
