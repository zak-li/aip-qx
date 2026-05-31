"""
cli/api/events.py
-----------------
Server-Sent Events client for /api/v1/events/stream.

Two entry points:

  * `sse_client` — long-running asyncio task used by the Textual dashboard
    (consumes events into an asyncio.Queue).
  * `stream_events()` — synchronous generator used by the `pxtly events stream`
    command (prints lines as they arrive).

Both use the persisted Bearer token from the keyring; no refresh logic is
applied to the stream itself because httpx/asyncio cannot retroactively
swap headers on an open response. If the stream returns 401 the loop
reconnects and the auth header is fetched fresh — which will trigger the
PxtlyAuth middleware refresh on the *next* normal request.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Iterator
from dataclasses import dataclass, field

import httpx

from cli.security.tokens import get_access_token
from cli.settings import settings

log = logging.getLogger(__name__)

_MAX_QUEUE = 500


@dataclass
class SseEvent:
    ts: float
    event_type: str
    payload: dict[str, object] = field(default_factory=dict)
    raw: str = ""

    def label(self) -> str:
        return self.event_type.upper().replace("_", " ")


class SseClient:
    """Long-running SSE consumer for the dashboard."""

    def __init__(self, url: str) -> None:
        self._url = url
        self._task: asyncio.Task[None] | None = None
        self._queue: asyncio.Queue[SseEvent] | None = None
        self._connected = False
        self._total_received = 0

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def events_received(self) -> int:
        return self._total_received

    def _get_queue(self) -> asyncio.Queue[SseEvent]:
        if self._queue is None:
            self._queue = asyncio.Queue(maxsize=_MAX_QUEUE)
        return self._queue

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.ensure_future(self._run_loop())
        log.info("SSE background task started -> %s", self._url)

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._connected = False
        self._queue = None

    async def get_event(self) -> SseEvent | None:
        q = self._get_queue()
        try:
            return q.get_nowait()
        except asyncio.QueueEmpty:
            return None

    async def _run_loop(self) -> None:
        while True:
            try:
                await self._connect_and_read()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._connected = False
                log.warning(
                    "SSE disconnected: %s — retrying in %.0fs",
                    exc, settings.sse_reconnect_delay,
                )
                await asyncio.sleep(settings.sse_reconnect_delay)

    async def _connect_and_read(self) -> None:
        headers = _stream_headers()
        async with httpx.AsyncClient(
            verify=settings.verify_param,
            timeout=httpx.Timeout(None, connect=10.0),
        ) as client:
            async with client.stream("GET", self._url, headers=headers) as response:
                if response.status_code != 200:
                    raise RuntimeError(f"SSE endpoint returned HTTP {response.status_code}")
                self._connected = True
                q = self._get_queue()
                for event in _parse_event_stream(response.aiter_lines()):
                    self._total_received += 1
                    if q.full():
                        try:
                            q.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                    await q.put(event)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _stream_headers() -> dict[str, str]:
    headers = {"Accept": "text/event-stream", "Cache-Control": "no-cache"}
    token = get_access_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def _parse_event_stream(lines):
    """SSE framing — accumulate `event:` and `data:` lines into one event."""
    event_type = "message"
    data_lines: list[str] = []
    async for raw_line in lines:
        line = raw_line.strip()
        if line.startswith("event:"):
            event_type = line[6:].strip() or "message"
        elif line.startswith("data:"):
            data_lines.append(line[5:].strip())
        elif line == "" and data_lines:
            ts = time.time()
            raw = "\n".join(data_lines)
            try:
                payload = json.loads(raw)
                etype = event_type or payload.get("type", "message")
                yield SseEvent(ts=ts, event_type=str(etype), payload=payload, raw=raw)
            except json.JSONDecodeError:
                yield SseEvent(ts=ts, event_type=event_type, raw=raw)
            event_type = "message"
            data_lines = []


def stream_events(max_events: int | None = None) -> Iterator[SseEvent]:
    """
    Synchronous generator used by `pxtly events stream`. Yields SseEvent
    objects. Reconnects on transient errors; surfaces a clean exit on
    KeyboardInterrupt.
    """
    received = 0
    headers = _stream_headers()
    while True:
        try:
            with httpx.Client(
                verify=settings.verify_param,
                timeout=httpx.Timeout(None, connect=10.0),
            ) as client:
                with client.stream("GET", settings.sse_url, headers=headers) as response:
                    if response.status_code != 200:
                        raise RuntimeError(f"SSE returned HTTP {response.status_code}")
                    event_type = "message"
                    data_lines: list[str] = []
                    for raw_line in response.iter_lines():
                        line = raw_line.strip() if isinstance(raw_line, str) else raw_line.decode("utf-8", "replace").strip()
                        if line.startswith("event:"):
                            event_type = line[6:].strip() or "message"
                        elif line.startswith("data:"):
                            data_lines.append(line[5:].strip())
                        elif line == "" and data_lines:
                            ts = time.time()
                            raw = "\n".join(data_lines)
                            try:
                                payload = json.loads(raw)
                                etype = event_type or payload.get("type", "message")
                                ev = SseEvent(ts=ts, event_type=str(etype), payload=payload, raw=raw)
                            except json.JSONDecodeError:
                                ev = SseEvent(ts=ts, event_type=event_type, raw=raw)
                            yield ev
                            received += 1
                            if max_events and received >= max_events:
                                return
                            event_type = "message"
                            data_lines = []
        except KeyboardInterrupt:
            return
        except Exception as exc:
            log.warning("SSE stream error: %s — reconnecting in %.0fs", exc, settings.sse_reconnect_delay)
            time.sleep(settings.sse_reconnect_delay)


sse_client: SseClient = SseClient(settings.sse_url)
