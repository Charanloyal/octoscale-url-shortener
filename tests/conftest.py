import asyncio
from typing import AsyncGenerator
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from httpx import AsyncClient, ASGITransport

# Override database URL for testing BEFORE importing app
from app.config import settings
settings.DATABASE_URL = "sqlite+aiosqlite:///:memory:"

from app.database import Base, get_db
from app.redis import get_redis, redis_manager
from app.main import app as fastapi_app

# Create test engine using SQLite in-memory database
test_engine = create_async_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False}
)

TestAsyncSessionLocal = async_sessionmaker(
    bind=test_engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=AsyncSession
)
# Override AsyncSessionLocal in app.database module for background tasks
import app.database
app.database.AsyncSessionLocal = TestAsyncSessionLocal

# ----------------------------------------------------
# Mock Redis Implementation
# ----------------------------------------------------
class MockRedisPipeline:
    def __init__(self, mock_redis):
        self.mock_redis = mock_redis
        self.commands = []

    def zremrangebyscore(self, key, min_val, max_val):
        def cmd():
            zset = self.mock_redis.store.setdefault(key, {})
            # filter out members with score between min and max
            keys_to_remove = [k for k, v in zset.items() if min_val <= v <= max_val]
            for k in keys_to_remove:
                del zset[k]
            return len(keys_to_remove)
        self.commands.append(cmd)
        return self

    def zadd(self, key, mapping):
        def cmd():
            zset = self.mock_redis.store.setdefault(key, {})
            for member, score in mapping.items():
                zset[member] = float(score)
            return len(mapping)
        self.commands.append(cmd)
        return self

    def zcard(self, key):
        def cmd():
            zset = self.mock_redis.store.setdefault(key, {})
            return len(zset)
        self.commands.append(cmd)
        return self

    def expire(self, key, seconds):
        def cmd():
            return 1
        self.commands.append(cmd)
        return self

    async def execute(self):
        results = []
        for cmd in self.commands:
            results.append(cmd())
        self.commands.clear()
        return results


class MockRedis:
    def __init__(self):
        self.store = {}
        self.counter = 10000000

    async def ping(self):
        return True

    async def exists(self, key):
        return key in self.store

    async def get(self, key):
        val = self.store.get(key)
        return str(val) if val is not None else None

    async def set(self, key, value):
        self.store[key] = value
        return True

    async def setex(self, key, ttl, value):
        self.store[key] = value
        return True

    async def incr(self, key):
        val = self.store.get(key)
        if val is None:
            if key == "url_id_counter":
                self.counter += 1
                current = self.counter
            else:
                current = 1
        else:
            current = int(val) + 1
        self.store[key] = current
        if key == "url_id_counter":
            self.counter = current
        return current

    async def close(self):
        pass

    def pipeline(self):
        return MockRedisPipeline(self)


# Create single instance of MockRedis
mock_redis_client = MockRedis()

# Override dependencies
async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestAsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def override_get_redis() -> MockRedis:
    return mock_redis_client

fastapi_app.dependency_overrides[get_db] = override_get_db
fastapi_app.dependency_overrides[get_redis] = override_get_redis


@pytest.fixture(scope="function", autouse=True)
async def setup_db():
    # Setup: Create tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield
    
    # Teardown: Drop tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with TestAsyncSessionLocal() as session:
        yield session

@pytest.fixture(scope="function")
def mock_redis() -> MockRedis:
    mock_redis_client.store.clear()
    mock_redis_client.counter = 10000000
    return mock_redis_client

@pytest.fixture(scope="function")
async def client() -> AsyncGenerator[AsyncClient, None]:
    # Mock redis manager initialize/close to avoid actual Redis connections
    redis_manager.redis = mock_redis_client
    
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app),
        base_url="http://test"
    ) as ac:
        yield ac
