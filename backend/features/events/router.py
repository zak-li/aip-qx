"""Live Fabric event feed via Server-Sent Events."""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from backend.core.redis_client import get_redis_pool
from backend.dependencies import get_current_user
from backend.features.auth.models import User

logger = logging.getLogger(__name__)

router = APIRouter()

_CHANNEL = "asset:events"
_HEARTBEAT_INTERVAL = 15


@router.get("/stream")
async def stream_events(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """SSE stream of live Hyperledger Fabric asset events."""

    async def generator():
        client = aioredis.Redis(connection_pool=get_redis_pool())
        pubsub = client.pubsub()
        await pubsub.subscribe(_CHANNEL)
        last_hb = time.monotonic()

        try:
            yield f"data: {json.dumps({'type': 'CONNECTED', 'ts': int(time.time())})}\n\n"

            while True:
                if await request.is_disconnected():
                    break

                now = time.monotonic()
                if now - last_hb >= _HEARTBEAT_INTERVAL:
                    yield ": heartbeat\n\n"
                    last_hb = now

                try:
                    msg = await asyncio.wait_for(
                        pubsub.get_message(ignore_subscribe_messages=True),
                        timeout=1.0,
                    )
                except TimeoutError:
                    continue

                if msg is None:
                    continue

                data = msg.get("data")
                if isinstance(data, bytes):
                    raw = data.decode("utf-8", errors="replace")
                elif isinstance(data, str):
                    raw = data
                else:
                    logger.warning("[EVENTS] Discarding non-string SSE payload: %r", type(data))
                    continue

                parts = raw.split(":", 1)
                if len(parts) != 2:
                    continue

                action, asset_id = parts
                payload = {
                    "id": str(uuid.uuid4()),
                    "type": action,
                    "asset_id": asset_id,
                    "ts": int(time.time()),
                }
                yield f"data: {json.dumps(payload)}\n\n"

        except Exception as exc:
            logger.error(f"[EVENTS] SSE error: {exc}")
            yield f"data: {json.dumps({'type': 'ERROR', 'message': 'Stream interrupted'})}\n\n"
        finally:
            try:
                await pubsub.unsubscribe(_CHANNEL)
                await pubsub.aclose()
                logger.debug("[EVENTS] SSE client disconnected, pubsub closed.")
            except Exception as exc:
                logger.warning(f"[EVENTS] Error closing pubsub: {exc}")
            await client.aclose()

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
