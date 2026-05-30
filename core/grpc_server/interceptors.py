"""gRPC server interceptors.

AuthInterceptor  — validates the Keycloak JWT from the `authorization` metadata key
                   (Bearer scheme), attaches the decoded payload to the context so
                   servicers can read ctx.user_payload["sub"] / ["qx_role"].

LoggingInterceptor — structured request/response logging.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

import grpc
import grpc.aio

from core.core.oidc import validate_token

logger = logging.getLogger(__name__)

# gRPC RPCs that do not require a token.
_PUBLIC_METHODS: frozenset[str] = frozenset()


class AuthInterceptor(grpc.aio.ServerInterceptor):
    """Validates the Keycloak Bearer JWT from the `authorization` metadata key.

    On success: injects `user_payload` into the context.
    On failure: aborts with UNAUTHENTICATED.
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
                payload = await validate_token(token)
            except ValueError as exc:
                await context.abort(grpc.StatusCode.UNAUTHENTICATED, str(exc))
                return

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
                logger.info("gRPC %s OK %.1fms", method, elapsed)
                return result
            except Exception as exc:
                elapsed = (time.perf_counter() - start) * 1000
                logger.error("gRPC %s ERROR %.1fms — %s", method, elapsed, exc)
                raise

        if handler.unary_unary:
            return handler._replace(unary_unary=logged_func)  # type: ignore[attr-defined]
        if handler.unary_stream:
            return handler._replace(unary_stream=logged_func)
        if handler.stream_unary:
            return handler._replace(stream_unary=logged_func)
        return handler._replace(stream_stream=logged_func)
