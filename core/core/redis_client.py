import asyncio
import json
import logging
from collections.abc import AsyncGenerator

import redis.asyncio as redis

from core.config import settings

logger = logging.getLogger(__name__)

# Per-event-loop connection pool cache.
#
# A single module-level ConnectionPool gets bound to whichever event loop first
# opens a connection: reusing it from a different loop raises
# "got Future attached to a different loop". Production runs one loop so a
# shared pool is fine, but pytest creates a fresh loop per test and would hit
# that error. Keying the pool by ``id(loop)`` gives prod its single shared pool
# and tests their own per-loop pools without any extra plumbing.
_pools: dict[int, redis.ConnectionPool] = {}


def _get_pool() -> redis.ConnectionPool:
    loop = asyncio.get_event_loop()
    key = id(loop)
    pool = _pools.get(key)
    if pool is None:
        pool = redis.ConnectionPool.from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=50,
        )
        _pools[key] = pool
    return pool


async def get_redis() -> AsyncGenerator[redis.Redis, None]:
    client = redis.Redis(connection_pool=_get_pool())
    try:
        yield client
    finally:
        await client.aclose()


async def get_redis_or_raise() -> redis.Redis:
    client = redis.Redis(connection_pool=_get_pool())
    try:
        await client.ping()
    except redis.ConnectionError as exc:
        await client.aclose()
        raise RuntimeError("Redis is unreachable") from exc
    return client


async def cache_get(key: str) -> str | None:
    client = redis.Redis(connection_pool=_get_pool())
    try:
        return await client.get(key)
    except redis.ConnectionError:
        logger.warning(f"Redis cache_get failed for key={key[:20]}")
        return None
    finally:
        await client.aclose()


async def cache_set(key: str, value: object, ttl: int = 30) -> None:
    client = redis.Redis(connection_pool=_get_pool())
    try:
        serialized = json.dumps(value, default=str)
        await client.setex(key, ttl, serialized)
    except redis.ConnectionError:
        logger.warning(f"Redis cache_set failed for key={key[:20]}")
    finally:
        await client.aclose()


async def publish(channel: str, message: object) -> bool:
    """Publish a message to a Redis channel with retries. Returns True on success.

    Failures are escalated to ERROR on the final attempt — callers that need
    delivery guarantees must check the return value rather than relying on a
    silent log line.
    """
    client = redis.Redis(connection_pool=_get_pool())
    retries = 3
    try:
        serialized = json.dumps(message, default=str)
        for attempt in range(retries):
            try:
                await client.publish(channel, serialized)
                return True
            except redis.ConnectionError as exc:
                if attempt == retries - 1:
                    logger.error(
                        "Redis publish failed after %d retries on channel=%s: %s",
                        retries, channel, exc,
                    )
                    return False
                logger.warning(
                    "Redis publish retry %d/%d on channel=%s",
                    attempt + 1, retries, channel,
                )
    finally:
        await client.aclose()
    return False


def get_redis_pool() -> redis.ConnectionPool:
    """Return the ConnectionPool for the current event loop."""
    return _get_pool()
