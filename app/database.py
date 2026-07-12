from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

# Create async engine
# Create async engine with dynamic options depending on dialect
engine_options = {}
if settings.DATABASE_URL.startswith("postgresql"):
    engine_options["pool_size"] = 20
    engine_options["max_overflow"] = 10

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    **engine_options
)

# Async session maker
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=AsyncSession
)

class Base(DeclarativeBase):
    pass

# Dependency to get db session
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
