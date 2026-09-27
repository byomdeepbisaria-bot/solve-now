import json
import logging
from typing import AsyncGenerator
import redis.asyncio as redis
from core.config import settings

logger = logging.getLogger(__name__)

# Global async Redis connection pool
redis_client = None


async def init_redis():
    """
    Initialise the async Redis client from the canonical REDIS_CONNECTION_URL.

    For Upstash (rediss://): TLS is negotiated automatically by the redis:// URL
    scheme.  We do NOT pass ssl_cert_reqs here because:
      - redis-py >=4 handles TLS via the URL scheme automatically.
      - Passing ssl_cert_reqs as a keyword arg to from_url() is not part of the
        stable public API and was causing "Redis URL must specify one of the
        following schemes" errors in some redis-py versions when the URL was
        invalid or empty.
    """
    global redis_client
    url = settings.REDIS_CONNECTION_URL

    # Defensive: the validator in config.py should catch invalid URLs at startup,
    # but guard here too so we get a clear error rather than a redis-py crash.
    valid_schemes = ("redis://", "rediss://", "unix://")
    if not any(url.startswith(s) for s in valid_schemes):
        raise ValueError(
            f"REDIS_CONNECTION_URL has an invalid scheme. "
            f"Set REDIS_URL on Render to your full Upstash URL (rediss://...). "
            f"Current scheme prefix: {url[:20]!r}"
        )

    redis_client = redis.Redis.from_url(url, decode_responses=True)

    # Test connectivity — raises if the server is unreachable.
    await redis_client.ping()
    scheme = url.split("://")[0]
    logger.info(f"Async Redis connected (scheme={scheme})")


async def get_redis() -> redis.Redis:
    if not redis_client:
        await init_redis()
    return redis_client


class RedisPubSubManager:
    """
    Manages broadcasting messages across multiple workers using Redis Pub/Sub.
    """

    def __init__(self):
        pass

    async def publish(self, channel: str, message: dict):
        client = await get_redis()
        await client.publish(channel, json.dumps(message))

    async def subscribe(self, channel: str) -> AsyncGenerator[dict, None]:
        client = await get_redis()
        pubsub = client.pubsub()
        await pubsub.subscribe(channel)
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    yield json.loads(message["data"])
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()


pubsub_manager = RedisPubSubManager()
