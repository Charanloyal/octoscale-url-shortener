from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.schemas.url import URLCreate, URLResponse, URLAnalyticsResponse
from app.api.dependencies import get_url_service, rate_limiter
from app.services.url_service import URLService
from app.database import get_db
from app.redis import get_redis
from app.config import settings

router = APIRouter(dependencies=[Depends(rate_limiter)])

@router.post("/shorten", response_model=URLResponse, status_code=status.HTTP_201_CREATED)
async def shorten_url(
    payload: URLCreate,
    service: URLService = Depends(get_url_service)
):
    """Create a shortened URL from a long URL."""
    try:
        url_record, _ = await service.shorten_url(payload.original_url, payload.custom_code)
        short_url = f"{settings.BASE_URL.rstrip('/')}/{url_record.short_code}"
        return URLResponse(
            original_url=url_record.original_url,
            short_code=url_record.short_code,
            short_url=short_url,
            clicks=url_record.clicks,
            created_at=url_record.created_at
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.get("/analytics/{short_code}", response_model=URLAnalyticsResponse)
async def get_url_analytics(
    short_code: str,
    service: URLService = Depends(get_url_service)
):
    """Retrieve detailed click analytics for a short code."""
    try:
        url_record = await service.get_analytics(short_code)
        
        # Sort analytics in memory descending by clicked_at, and limit to recent 100
        recent = sorted(url_record.analytics, key=lambda x: x.clicked_at, reverse=True)[:100]
        
        return URLAnalyticsResponse(
            short_code=url_record.short_code,
            original_url=url_record.original_url,
            clicks=url_record.clicks,
            created_at=url_record.created_at,
            recent_clicks=recent
        )
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Short URL not found")

@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check(
    db: AsyncSession = Depends(get_db),
    redis_client: aioredis.Redis = Depends(get_redis)
):
    """Check connectivity to PostgreSQL and Redis."""
    health_status = {"status": "healthy", "components": {}}
    
    # Check Database
    try:
        from sqlalchemy import text
        await db.execute(text("SELECT 1"))
        health_status["components"]["database"] = "up"
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["components"]["database"] = f"down: {str(e)}"
        
    # Check Redis
    try:
        await redis_client.ping()
        health_status["components"]["redis"] = "up"
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["components"]["redis"] = f"down: {str(e)}"
        
    if health_status["status"] == "unhealthy":
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=health_status)
        
    return health_status
