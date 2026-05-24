import asyncio
import ipaddress
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

import hvac
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from core.api.middleware.auth_middleware import AuthMiddleware
from core.api.middleware.rate_limiter import RateLimiterMiddleware
from core.api.middleware.request_logger import RequestLoggerMiddleware
from core.api.v1.router import api_router
from core.config import settings
from core.core.database import AsyncSessionLocal, engine
from core.core.logging_config import setup_logging
from core.core.metrics import (
    RWA_AML_SCORE,
    RWA_ASSETS_BY_STATUS,
    RWA_KYC_EXPIRING,
)
from core.core.redis_client import get_redis
from core.dependencies import get_fabric
from core.exceptions import setup_global_exception_handlers
from core.fabric_client.events import FabricEventListener
from core.features.agent.groq_client import close_client as close_groq_client
from core.features.fraud_detection.neo4j_sync import get_neo4j_client

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

    _startup_status: dict[str, str] = {}

    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("PostgreSQL connection verified.")
        _startup_status["postgres"] = "ok"
    except Exception as exc:
        logger.error(f"PostgreSQL connection failed: {exc}")
        _startup_status["postgres"] = "FAILED"

    redis_gen = get_redis()
    try:
        redis_conn = await redis_gen.__anext__()
        await redis_conn.ping()  # type: ignore
        logger.info("Redis connection verified.")
        _startup_status["redis"] = "ok"
    except Exception as exc:
        logger.error(f"Redis connection failed: {exc}")
        _startup_status["redis"] = "FAILED"
    finally:
        await redis_gen.aclose()

    try:
        await get_fabric().connect()
        logger.info("Hyperledger Fabric gRPC channel connected.")
        _startup_status["fabric"] = "ok"
    except Exception as exc:
        # Fabric may be unavailable if the network hasn't started yet —
        # this is non-fatal; the circuit breaker will retry on first use.
        logger.warning(f"Fabric connection deferred (non-fatal): {exc}")
        _startup_status["fabric"] = "deferred"

    neo4j_client = get_neo4j_client()
    try:
        await neo4j_client.connect()
        logger.info("Neo4j graph database connected.")
        _startup_status["neo4j"] = "ok"
    except Exception as exc:
        logger.warning(f"Neo4j connection deferred (non-fatal): {exc}")
        _startup_status["neo4j"] = "deferred"

    global _event_listener_instance
    _event_listener_instance = FabricEventListener(settings)
    try:
        await _event_listener_instance.start()
        logger.info("Fabric event listener started.")
        _startup_status["events"] = "ok"
    except Exception as exc:
        logger.warning(f"Fabric event listener deferred (non-fatal): {exc}")
        _startup_status["events"] = "deferred"

    # Single summary line for quick operational assessment.
    summary = " | ".join(f"{k}={v}" for k, v in _startup_status.items())
    logger.info(f"Startup complete — {summary}")

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
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-Requested-With",
        "X-CSRF-Token",
        "Accept",
        "Origin",
    ],
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


# Subnets allowed to reach /metrics and /health/deep without auth.
# Covers loopback + every RFC1918 private range so the API can be scraped
# from the host (10.10.10.*), a Docker bridge (172.16-31.*), or a corporate
# LAN (192.168.*).
_INTERNAL_NETWORKS: tuple[ipaddress.IPv4Network, ...] = (
    ipaddress.IPv4Network("127.0.0.0/8"),
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("172.16.0.0/12"),
    ipaddress.IPv4Network("192.168.0.0/16"),
)


def _is_trusted_internal(client_ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    if not isinstance(addr, ipaddress.IPv4Address):
        return False
    return any(addr in net for net in _INTERNAL_NETWORKS)


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

    redis_gen = get_redis()
    try:
        redis_conn = await redis_gen.__anext__()
        await redis_conn.ping()  # type: ignore
        checks["redis"] = "ok"
    except Exception:
        logger.exception("health: redis check failed")
        checks["redis"] = "error"
        overall_ok = False
    finally:
        await redis_gen.aclose()

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
        vault_client = hvac.Client(url=settings.vault_addr, token=settings.vault_token.get_secret_value())
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
