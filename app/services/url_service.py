import redis.asyncio as aioredis
from typing import Optional, Tuple
from sqlalchemy import select, func
from app.models.url import URL
from app.repositories.url_repository import URLRepository
from app.logger import logger

BASE62_ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
COUNTER_START = 10000000  # Start counter here to ensure short codes are at least 5 chars

def encode_base62(num: int) -> str:
    """Encode an integer to a Base62 string."""
    if num == 0:
        return BASE62_ALPHABET[0]
    arr = []
    while num:
        num, rem = divmod(num, 62)
        arr.append(BASE62_ALPHABET[rem])
    arr.reverse()
    return "".join(arr)

class URLService:
    def __init__(self, repository: URLRepository, redis_client: aioredis.Redis):
        self.repo = repository
        self.redis = redis_client

    async def _get_next_id(self) -> int:
        """Get next ID from Redis counter, falling back to PostgreSQL if not set."""
        counter_exists = await self.redis.exists("url_id_counter")
        if not counter_exists:
            # Fallback: Query max ID from PostgreSQL
            result = await self.repo.db.execute(select(func.max(URL.id)))
            max_id = result.scalar() or 0
            start_val = max(max_id, COUNTER_START)
            # Initialize redis counter
            await self.redis.set("url_id_counter", start_val)
            logger.info("initialized_redis_counter", value=start_val)
        
        next_id = await self.redis.incr("url_id_counter")
        return next_id

    async def shorten_url(self, original_url: str, custom_code: Optional[str] = None) -> Tuple[URL, bool]:
        """
        Shorten a URL. Returns a tuple of (URL, created_new).
        Checks cache and database first to avoid duplicate shortening.
        """
        # 1. If custom code is provided, handle separately
        if custom_code:
            # Check Redis for custom code first
            cached_url = await self.redis.get(f"code:{custom_code}")
            if cached_url:
                raise ValueError("Custom code already in use")

            # Check DB for custom code
            existing = await self.repo.get_by_short_code(custom_code)
            if existing:
                raise ValueError("Custom code already in use")

            # Create new mapping
            new_url = URL(original_url=original_url, short_code=custom_code)
            created_url = await self.repo.create(new_url)
            
            # Cache in Redis (TTL: 24h)
            await self.redis.setex(f"code:{custom_code}", 86400, original_url)
            await self.redis.setex(f"orig:{original_url}", 86400, custom_code)
            
            logger.info("url_shortened_custom", original_url=original_url, short_code=custom_code)
            return created_url, True

        # 2. Check Redis for existing shortened URL
        cached_code = await self.redis.get(f"orig:{original_url}")
        if cached_code:
            existing_db = await self.repo.get_by_short_code(cached_code)
            if existing_db:
                logger.debug("cache_hit_original", original_url=original_url, short_code=cached_code)
                return existing_db, False

        # 3. Check DB for existing shortened URL
        existing_db = await self.repo.get_by_original_url(original_url)
        if existing_db:
            # Populate Redis cache
            await self.redis.setex(f"code:{existing_db.short_code}", 86400, original_url)
            await self.redis.setex(f"orig:{original_url}", 86400, existing_db.short_code)
            logger.debug("db_hit_original", original_url=original_url, short_code=existing_db.short_code)
            return existing_db, False

        # 4. Generate a new short code using Redis counter + Base62
        next_id = await self._get_next_id()
        short_code = encode_base62(next_id)

        # 5. Save to database
        new_url = URL(id=next_id, original_url=original_url, short_code=short_code)
        created_url = await self.repo.create(new_url)

        # 6. Cache mappings in Redis
        await self.redis.setex(f"code:{short_code}", 86400, original_url)
        await self.redis.setex(f"orig:{original_url}", 86400, short_code)

        logger.info("url_shortened", original_url=original_url, short_code=short_code, internal_id=next_id)
        return created_url, True

    async def resolve_url(self, short_code: str) -> str:
        """
        Resolve a short code to its original URL.
        Uses Redis cache first for super-fast lookups.
        Throws KeyError if code is invalid.
        """
        # 1. Read from Redis cache
        cached_url = await self.redis.get(f"code:{short_code}")
        if cached_url:
            logger.debug("cache_hit_resolve", short_code=short_code)
            return cached_url

        # 2. Read from Database
        url_record = await self.repo.get_by_short_code(short_code)
        if not url_record:
            logger.warn("resolve_failed_not_found", short_code=short_code)
            raise KeyError("Short code not found")

        # 3. Populate cache
        await self.redis.setex(f"code:{short_code}", 86400, url_record.original_url)
        await self.redis.setex(f"orig:{url_record.original_url}", 86400, short_code)
        
        logger.info("db_hit_resolve", short_code=short_code, original_url=url_record.original_url)
        return url_record.original_url

    async def record_click(self, short_code: str, referrer: Optional[str], user_agent: Optional[str]) -> None:
        """
        Record a click event: increments DB count and registers analytic event.
        Typically run in a FastAPI background task to avoid slowing down redirect.
        """
        url_record = await self.repo.get_by_short_code(short_code)
        if url_record:
            await self.repo.increment_clicks(url_record.id)
            await self.repo.create_click_analytic(url_record.id, referrer, user_agent)
            logger.info("click_recorded", short_code=short_code, referrer=referrer)

    async def get_analytics(self, short_code: str) -> URL:
        """Get analytics including recent click logs."""
        url_record = await self.repo.get_by_short_code(short_code)
        if not url_record:
            raise KeyError("Short code not found")
        return url_record
