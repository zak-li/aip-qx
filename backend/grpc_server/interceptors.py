"""gRPC server interceptors.

AuthInterceptor  — validates the JWT from the `authorization` metadata key,
                   attaches the decoded payload to the ServicerContext so
                   servicers can call ctx.user_payload.
LoggingInterceptor — structured request/response logging mirroring the
                     behaviour of the former RequestLoggerMiddleware.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

import grpc
import grpc.aio

from backend.core.security import decode_token

logger = logging.getLogger(__name__)

# RPCs that do not require authentication (public endpoints).
_PUBLIC_METHODS = frozenset({
    "/rwa.auth.AuthService/Login",
})


class AuthInterceptor(grpc.aio.ServerInterceptor):
    """Validates Bearer JWT from the `authorization` metadata key.

    On success, injects `user_payload` into the servicer context via
    context.user_payload so downstream servicers can read user.id / role.
    On failure, aborts with UNAUTHENTICATED.
    """

    async def intercept_service(
        self,
        continuation: Callable,
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler:
        if handler_call_details.method in _PUBLIC_METHODS:
            return await continuation(handler_call_details)

        return _AuthHandler(await continuation(handler_call_details))


class _AuthHandler(grpc.RpcMethodHandler):
    def __init__(self, handler: grpc.RpcMethodHandler) -> None:
        self._handler = handler
        # Mirror all RpcMethodHandler attributes.
        self.request_streaming = handler.request_streaming
        self.response_streaming = handler.response_streaming
        self.request_deserializer = handler.request_deserializer
        self.response_serializer = handler.response_serializer
        self.unary_unary = self._wrap(handler.unary_unary) if handler.unary_unary else None
        self.unary_stream = self._wrap(handler.unary_stream) if handler.unary_stream else None
        self.stream_unary = self._wrap(handler.stream_unary) if handler.stream_unary else None
        self.stream_stream = self._wrap(handler.stream_stream) if handler.stream_stream else None

    def _wrap(self, func: Callable) -> Callable:
        async def wrapper(request_or_iterator: Any, context: grpc.aio.ServicerContext) -> Any:
            token = _extract_token(context)
            if not token:
                await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Missing authorization token")
                return

            try:
                payload = decode_token(token)
            except ValueError as exc:
                await context.abort(grpc.StatusCode.UNAUTHENTICATED, str(exc))
                return

            # Attach decoded payload so servicers can read it.
            context.user_payload = payload  # type: ignore[attr-defined]
            return await func(request_or_iterator, context)

        return wrapper


def _extract_token(context: grpc.aio.ServicerContext) -> str | None:
    for key, value in context.invocation_metadata():
        if key == "authorization" and value.startswith("Bearer "):
            return value[len("Bearer "):]
    return None


class LoggingInterceptor(grpc.aio.ServerInterceptor):
    """Logs method, duration, and final status code for every RPC call."""

    async def intercept_service(
        self,
        continuation: Callable,
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler:
        handler = await continuation(handler_call_details)
        if handler is None:
            return handler

        method = handler_call_details.method

        original_func = (
            handler.unary_unary
            or handler.unary_stream
            or handler.stream_unary
            or handler.stream_stream
        )

        if original_func is None:
            return handler

        async def logged_func(request_or_iterator: Any, context: grpc.aio.ServicerContext) -> Any:
            start = time.perf_counter()
            try:
                result = await original_func(request_or_iterator, context)
                elapsed = (time.perf_counter() - start) * 1000
                logger.info(f"gRPC {method} OK {elapsed:.1f}ms")
                return result
            except Exception as exc:
                elapsed = (time.perf_counter() - start) * 1000
                logger.error(f"gRPC {method} ERROR {elapsed:.1f}ms — {exc}")
                raise

        # Rebuild the handler with the wrapped function.
        if handler.unary_unary:
            return handler._replace(unary_unary=logged_func)  # type: ignore[attr-defined]
        if handler.unary_stream:
            return handler._replace(unary_stream=logged_func)
        if handler.stream_unary:
            return handler._replace(stream_unary=logged_func)
        return handler._replace(stream_stream=logged_func)
