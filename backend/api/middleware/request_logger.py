import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from backend.core.client_ip import extract_client_ip, set_request_ip

logger = logging.getLogger(__name__)


class RequestLoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        start_time = time.time()
        # Resolve the client IP once and stash it on both request.state and a
        # contextvar so downstream handlers (audit logs, rate limiter, deep
        # services) share a single trusted value.
        request.state.client_ip = extract_client_ip(request)
        set_request_ip(request.state.client_ip)

        response = await call_next(request)

        duration_ms = int((time.time() - start_time) * 1000)
        user_id = getattr(request.state, "user_id", None)

        logger.info(
            f"{request.method} {request.url.path} {response.status_code} {duration_ms}ms "
            f"ip={request.state.client_ip} "
            f"user={user_id or 'anonymous'}"
        )

        return response
