import time
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.database import get_db
from app.redis import get_redis
from app.repositories.url_repository import URLRepository
from app.services.url_service import URLService
from app.config import settings
from app.logger import logger

async def get_url_service(
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis)
) -> URLService:
    repo = URLRepository(db)
    return URLService(repo, redis)

async def rate_limiter(request: Request, redis: aioredis.Redis = Depends(get_redis)):
    """
    Sliding window rate limiter using Redis sorted sets.
    Limits requests per client IP to prevent service abuse.
    """
    # Exclude static files and frontend routes from rate limiting to speed up UI loading
    if request.url.path.startswith(("/static", "/templates", "/favicon.ico")) or request.url.path == "/":
        return

    client_ip = request.client.host if request.client else "unknown"
    key = f"rate_limit:{client_ip}"
    
    now = time.time()
    clear_before = now - 60  # 1 minute window
    
    try:
        # Create pipeline for atomic execution
        pipe = redis.pipeline()
        # Remove elements older than 1 minute
        pipe.zremrangebyscore(key, 0, clear_before)
        # Add current request timestamp
        pipe.zadd(key, {str(now): now})
        # Get count of requests in last 1 minute
        pipe.zcard(key)
        # Set expiration on the key to cleanup inactive IPs
        pipe.expire(key, 60)
        
        _, _, request_count, _ = await pipe.execute()
        
        if request_count > settings.RATE_LIMIT_PER_MINUTE:
            logger.warn("rate_limit_exceeded", ip=client_ip, path=request.url.path, count=request_count)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again in a minute."
            )
            
    except HTTPException:
        raise
    except Exception as e:
        # Fallback: if Redis rate limiting fails, log error and allow request (fail open to prevent complete outage)
        logger.error("rate_limiter_failed", error=str(e))
