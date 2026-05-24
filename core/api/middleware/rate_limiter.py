import hashlib
import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from core.core.client_ip import extract_client_ip
from core.core.redis_client import get_redis

logger = logging.getLogger(__name__)

GET_RATE_LIMIT = 120
WRITE_RATE_LIMIT = 30
WINDOW_SECONDS = 60

_EXEMPT_PREFIXES = ("/health", "/metrics")


class RateLimiterMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        path = request.url.path
        if any(path.startswith(p) for p in _EXEMPT_PREFIXES):
            return await call_next(request)

        method = request.method
        ip = getattr(request.state, "client_ip", None) or extract_client_ip(request)
        ip_hash = hashlib.sha256(ip.encode("utf-8")).hexdigest()[:16]
        key = f"rate:{ip_hash}:{method}"
        limit = GET_RATE_LIMIT if method == "GET" else WRITE_RATE_LIMIT
        now = time.time()

        try:
            async for redis_conn in get_redis():
                async with redis_conn.pipeline(transaction=True) as pipe:
                    await pipe.zremrangebyscore(key, 0, now - WINDOW_SECONDS)
                    await pipe.zadd(key, {str(now): now})
                    await pipe.zcard(key)
                    await pipe.expire(key, WINDOW_SECONDS)
                    results = await pipe.execute()

                req_count = results[2]
                if req_count > limit:
                    logger.warning(f"Rate limit exceeded: ip_hash={ip_hash} method={method} count={req_count}")
                    return JSONResponse(
                        status_code=429,
                        content={
                            "error": "TooManyRequests",
                            "message": f"Limite de {limit} requêtes/{WINDOW_SECONDS}s dépassée.",
                        },
                        headers={"Retry-After": str(WINDOW_SECONDS)},
                    )
                break

        except Exception as exc:
            logger.error(f"Rate limiter Redis indisponible: {exc}")
            if method not in ("GET", "HEAD", "OPTIONS"):
                return JSONResponse(
                    status_code=503,
                    content={
                        "error": "ServiceUnavailable",
                        "message": "Service temporairement indisponible, veuillez réessayer.",
                    },
                )

        return await call_next(request)
