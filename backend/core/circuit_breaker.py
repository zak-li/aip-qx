"""Generic circuit breaker for outbound dependencies.

The Fabric subsystem already has its own retry decorator with circuit
breaker (`backend.fabric_client.retry`). This module provides the same
guarantees for the other outbound dependencies — Neo4j, Vault, Groq —
so a flapping or completely down third-party never starves the worker
pool with synchronous timeouts.

States:
    CLOSED    — normal operation; failures are counted in a sliding window
    OPEN      — rejecting calls; transitions to HALF_OPEN after `cooldown_s`
    HALF_OPEN — one probe call is allowed; success → CLOSED, failure → OPEN
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import TypeVar

from prometheus_client import Counter, Gauge

logger = logging.getLogger(__name__)

T = TypeVar("T")


_CB_STATE = Gauge(
    "rwa_circuit_breaker_state",
    "Circuit breaker state per component (0 closed, 1 half-open, 2 open).",
    ["component"],
)
_CB_REJECTIONS = Counter(
    "rwa_circuit_breaker_rejections_total",
    "Calls rejected because the circuit was open.",
    ["component"],
)
_CB_FAILURES = Counter(
    "rwa_circuit_breaker_failures_total",
    "Outbound failures recorded by the circuit breaker.",
    ["component"],
)


class State(Enum):
    CLOSED = 0
    HALF_OPEN = 1
    OPEN = 2


class CircuitBreakerOpenError(Exception):
    """Raised when the circuit is open and calls are being rejected."""


class CircuitBreaker:
    """Async circuit breaker.

    Args:
        name:        component identifier used in metrics labels
        threshold:   consecutive failures before opening
        cooldown_s:  seconds to wait in OPEN before allowing a probe
        call_timeout_s: per-call timeout enforced via asyncio.wait_for
    """

    def __init__(
        self,
        name: str,
        *,
        threshold: int = 5,
        cooldown_s: float = 30.0,
        call_timeout_s: float = 10.0,
    ) -> None:
        self.name = name
        self._threshold = threshold
        self._cooldown_s = cooldown_s
        self._timeout_s = call_timeout_s

        self._state = State.CLOSED
        self._failure_count = 0
        self._opened_at = 0.0
        self._lock = asyncio.Lock()

        _CB_STATE.labels(component=name).set(0)

    def _set_state(self, state: State) -> None:
        self._state = state
        _CB_STATE.labels(component=self.name).set(state.value)

    async def call(self, fn: Callable[..., Awaitable[T]], *args: object, **kwargs: object) -> T:
        """Run `fn(*args, **kwargs)` under the breaker."""
        async with self._lock:
            now = time.monotonic()
            if self._state is State.OPEN:
                if now - self._opened_at < self._cooldown_s:
                    _CB_REJECTIONS.labels(component=self.name).inc()
                    raise CircuitBreakerOpenError(
                        f"Circuit '{self.name}' is open; rejecting call."
                    )
                # Probe — let one call through.
                self._set_state(State.HALF_OPEN)
                logger.info("Circuit '%s' transitioning to HALF_OPEN", self.name)

        try:
            result = await asyncio.wait_for(fn(*args, **kwargs), timeout=self._timeout_s)
        except Exception as exc:
            await self._record_failure(exc)
            raise

        async with self._lock:
            self._failure_count = 0
            if self._state is not State.CLOSED:
                logger.info("Circuit '%s' closing after successful probe", self.name)
                self._set_state(State.CLOSED)
        return result

    async def _record_failure(self, exc: BaseException) -> None:
        _CB_FAILURES.labels(component=self.name).inc()
        async with self._lock:
            self._failure_count += 1
            if (
                self._state is State.HALF_OPEN
                or self._failure_count >= self._threshold
            ):
                self._set_state(State.OPEN)
                self._opened_at = time.monotonic()
                logger.warning(
                    "Circuit '%s' OPEN after %d failure(s) (last: %s)",
                    self.name,
                    self._failure_count,
                    type(exc).__name__,
                )


# Pre-built breakers for the standard outbound dependencies. Import these
# rather than constructing your own so metrics labels stay consistent.
neo4j_breaker = CircuitBreaker("neo4j", threshold=5, cooldown_s=30.0, call_timeout_s=10.0)
vault_breaker = CircuitBreaker("vault", threshold=3, cooldown_s=60.0, call_timeout_s=5.0)
groq_breaker = CircuitBreaker("groq", threshold=4, cooldown_s=20.0, call_timeout_s=60.0)
