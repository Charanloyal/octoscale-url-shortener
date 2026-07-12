from typing import AsyncGenerator, Optional
import redis.asyncio as aioredis
from app.config import settings
from app.logger import logger

class RedisManager:
    def __init__(self):
        self.redis: Optional[aioredis.Redis] = None

    def initialize(self):
        """Initialize Redis connection pool."""
        try:
            self.redis = aioredis.from_url(
                settings.REDIS_URL, 
                encoding="utf-8", 
                decode_responses=True
            )
            logger.info("redis_connected", url=settings.REDIS_URL)
        except Exception as e:
            logger.error("redis_connection_failed", error=str(e))
            raise e

    async def close(self):
        """Close connection pool."""
        if self.redis:
            await self.redis.close()
            logger.info("redis_disconnected")

    async def get_client(self) -> aioredis.Redis:
        if not self.redis:
            self.initialize()
        return self.redis

redis_manager = RedisManager()

async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    client = await redis_manager.get_client()
    yield client
