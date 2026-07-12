from typing import Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.url import URL, ClickAnalytic
from app.repositories.base import BaseRepository

class URLRepository(BaseRepository[URL]):
    def __init__(self, db: AsyncSession):
        super().__init__(URL, db)

    async def get_by_short_code(self, short_code: str) -> Optional[URL]:
        result = await self.db.execute(
            select(URL).filter(URL.short_code == short_code)
        )
        return result.scalars().first()

    async def get_by_original_url(self, original_url: str) -> Optional[URL]:
        result = await self.db.execute(
            select(URL).filter(URL.original_url == original_url)
        )
        return result.scalars().first()

    async def increment_clicks(self, url_id: int) -> None:
        await self.db.execute(
            update(URL).where(URL.id == url_id).values(clicks=URL.clicks + 1)
        )

    async def create_click_analytic(
        self, url_id: int, referrer: Optional[str], user_agent: Optional[str]
    ) -> ClickAnalytic:
        analytic = ClickAnalytic(
            url_id=url_id,
            referrer=referrer[:500] if referrer else None,
            user_agent=user_agent[:1000] if user_agent else None
        )
        self.db.add(analytic)
        await self.db.flush()
        return analytic
