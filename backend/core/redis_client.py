import json
import logging
from collections.abc import AsyncGenerator

import redis.asyncio as redis

from backend.config import settings

logger = logging.getLogger(__name__)

redis_pool = redis.ConnectionPool.from_url(
    settings.redis_url,
    decode_responses=True,
    max_connections=50,
)

async def get_redis() -> AsyncGenerator[redis.Redis, None]:
    client = redis.Redis.from_pool(redis_pool)
    try:
        yield client
    finally:
        await client.aclose()

async def get_redis_or_raise() -> redis.Redis:
    client = redis.Redis.from_pool(redis_pool)
    try:
        await client.ping()
    except redis.ConnectionError as exc:
        await client.aclose()
        raise RuntimeError("Redis is unreachable") from exc
    return client

async def cache_get(key: str) -> str | None:
    client = redis.Redis.from_pool(redis_pool)
    try:
        return await client.get(key)
    except redis.ConnectionError:
        logger.warning(f"Redis cache_get failed for key={key[:20]}")
        return None
    finally:
        await client.aclose()

async def cache_set(key: str, value: object, ttl: int = 30) -> None:
    client = redis.Redis.from_pool(redis_pool)
    try:
        serialized = json.dumps(value, default=str)
        await client.setex(key, ttl, serialized)
    except redis.ConnectionError:
        logger.warning(f"Redis cache_set failed for key={key[:20]}")
    finally:
        await client.aclose()

async def publish(channel: str, message: object) -> None:
    client = redis.Redis.from_pool(redis_pool)
    retries = 3
    for attempt in range(retries):
        try:
            serialized = json.dumps(message, default=str)
            await client.publish(channel, serialized)
            break
        except redis.ConnectionError:
            if attempt == retries - 1:
                logger.error(f"Redis publish failed after {retries} retries on channel={channel}")
            else:
                logger.warning(f"Redis publish retry {attempt + 1}/{retries} on channel={channel}")
    await client.aclose()
