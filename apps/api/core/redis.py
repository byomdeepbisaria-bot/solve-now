import json
from typing import AsyncGenerator
import redis.asyncio as redis
from core.config import settings

# Global Redis connection pool
redis_client = None

async def init_redis():
    global redis_client
    redis_client = redis.Redis.from_url(
        settings.REDIS_CONNECTION_URL,
        decode_responses=True,
        ssl_cert_reqs="none" if settings.REDIS_CONNECTION_URL.startswith("rediss://") else None
    )
    # Test connection
    await redis_client.ping()

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

