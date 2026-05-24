import asyncio
import json
import logging
import random
import time
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, TypeVar

import grpc
from prometheus_client import Counter, Histogram

from core.exceptions import FabricEndorsementError

T = TypeVar("T")

logger = logging.getLogger(__name__)

FABRIC_RETRY_ATTEMPTS = Counter(
    "fabric_retry_attempts_total",
    "Number of times a Fabric gRPC operation was retried internally.",
    ["function_name", "exception_type"],
)

FABRIC_CIRCUIT_BREAKER_TRIPS = Counter(
    "fabric_circuit_breaker_trips_total",
    "Total occurrences where the circuit breaker tripped due to consecutive faults.",
    ["function_name"],
)

FABRIC_RETRY_DELAY = Histogram(
    "fabric_retry_delay_seconds",
    "Time spent intentionally waiting in jitter/backoff loops before retrying.",
    ["function_name"],
)

class CircuitBreakerOpenError(Exception):
    pass

def fabric_retry(
    override_max_attempts: int | None = None,
    override_base_delay: float | None = None,
    override_factor: float | None = None,
    override_jitter: float | None = None,
    override_cb_threshold: int | None = None,
    override_cb_timeout: float | None = None,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        state = {
            "failure_count": 0,
            "first_failure_time": 0.0,
            "circuit_open": False,
            "circuit_open_time": 0.0,
        }

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            self_obj = args[0] if args else None
            func_settings = getattr(self_obj, "settings", None)

            if not func_settings and override_max_attempts is None:
                raise RuntimeError("Settings non injecté dans l'instance ni overrides fournis.")

            max_attempts = override_max_attempts if override_max_attempts is not None else func_settings.fabric_retry_max_attempts
            base_delay = override_base_delay if override_base_delay is not None else func_settings.fabric_retry_base_delay
            factor = override_factor if override_factor is not None else func_settings.fabric_retry_factor
            jitter = override_jitter if override_jitter is not None else func_settings.fabric_retry_jitter
            cb_threshold = override_cb_threshold if override_cb_threshold is not None else func_settings.fabric_retry_circuit_breaker_threshold
            cb_timeout = override_cb_timeout if override_cb_timeout is not None else func_settings.fabric_retry_circuit_breaker_timeout
            grpc_timeout = getattr(func_settings, "fabric_grpc_timeout", 30) if func_settings else 30

            now = time.time()

            if state["circuit_open"]:
                if now - state["circuit_open_time"] >= cb_timeout:
                    state["circuit_open"] = False
                    state["failure_count"] = 0
                else:
                    raise CircuitBreakerOpenError(f"Circuit breaker actif pour {func.__name__}")

            current_delay = base_delay
            latest_error: Exception | None = None

            for attempt in range(1, max_attempts + 1):
                try:
                    result = await asyncio.wait_for(func(*args, **kwargs), timeout=grpc_timeout)
                    state["failure_count"] = 0
                    state["circuit_open"] = False
                    return result
                except TimeoutError as exc:
                    latest_error = exc
                    exc_name = "TimeoutError"
                    FABRIC_RETRY_ATTEMPTS.labels(function_name=func.__name__, exception_type=exc_name).inc()
                except (grpc.RpcError, ConnectionError) as exc:
                    latest_error = exc
                    exc_name = type(exc).__name__
                    FABRIC_RETRY_ATTEMPTS.labels(function_name=func.__name__, exception_type=exc_name).inc()

                fail_time = time.time()

                if state["failure_count"] == 0 or (fail_time - state["first_failure_time"] > cb_timeout and not state["circuit_open"]):
                    state["failure_count"] = 1
                    state["first_failure_time"] = fail_time
                else:
                    state["failure_count"] += 1

                if state["failure_count"] >= cb_threshold:
                    state["circuit_open"] = True
                    state["circuit_open_time"] = fail_time
                    FABRIC_CIRCUIT_BREAKER_TRIPS.labels(function_name=func.__name__).inc()
                    raise CircuitBreakerOpenError(f"Circuit breaker déclenché pour {func.__name__}") from latest_error

                if attempt == max_attempts:
                    break

                wait_delay = current_delay + random.uniform(0, jitter)

                FABRIC_RETRY_DELAY.labels(function_name=func.__name__).observe(wait_delay)

                logger.warning(
                    json.dumps({
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "delay_next": wait_delay,
                        "exception_type": exc_name,
                        "function_name": func.__name__,
                    })
                )

                await asyncio.sleep(wait_delay)
                current_delay *= factor

            if latest_error:
                raise FabricEndorsementError(detail=str(latest_error)) from latest_error

            raise RuntimeError("Toutes les tentatives épuisées sans résultat.")

        return wrapper

    return decorator
