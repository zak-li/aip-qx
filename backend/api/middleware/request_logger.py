import logging
import time
from typing import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class RequestLoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        start_time = time.time()

        response = await call_next(request)

        duration_ms = int((time.time() - start_time) * 1000)
        user_id = getattr(request.state, "user_id", None)

        logger.info(
            f"{request.method} {request.url.path} {response.status_code} {duration_ms}ms "
            f"ip={request.client.host if request.client else '127.0.0.1'} "
            f"user={user_id or 'anonymous'}"
        )

        return response
