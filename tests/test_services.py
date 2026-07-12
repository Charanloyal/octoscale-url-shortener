import pytest
from app.services.url_service import URLService, encode_base62
from app.repositories.url_repository import URLRepository
from app.models.url import URL

def test_encode_base62():
    assert encode_base62(0) == "a"
    # Testing numeric encoding values
    assert len(encode_base62(10000000)) >= 4
    assert encode_base62(61) == "9"
    # Basic verification of bijectivity characteristics
    assert encode_base62(12345) != ""

@pytest.mark.asyncio
async def test_shorten_url_new(db_session, mock_redis):
    repo = URLRepository(db_session)
    service = URLService(repo, mock_redis)

    orig_url = "https://example.com/test-new"
    url_record, created = await service.shorten_url(orig_url)
    
    assert created is True
    assert url_record.id == 10000001
    assert url_record.original_url == orig_url
    assert url_record.short_code == encode_base62(10000001)

    # Check cache was populated
    assert await mock_redis.get(f"code:{url_record.short_code}") == orig_url
    assert await mock_redis.get(f"orig:{orig_url}") == url_record.short_code

@pytest.mark.asyncio
async def test_shorten_url_cached(db_session, mock_redis):
    repo = URLRepository(db_session)
    service = URLService(repo, mock_redis)

    orig_url = "https://example.com/test-cache"
    
    # Shorten once
    url1, created1 = await service.shorten_url(orig_url)
    assert created1 is True

    # Shorten again (should fetch from Redis cache)
    url2, created2 = await service.shorten_url(orig_url)
    assert created2 is False
    assert url1.id == url2.id
    assert url1.short_code == url2.short_code

@pytest.mark.asyncio
async def test_shorten_url_custom_code(db_session, mock_redis):
    repo = URLRepository(db_session)
    service = URLService(repo, mock_redis)

    orig_url = "https://example.com/custom"
    custom_code = "myurl"

    url_record, created = await service.shorten_url(orig_url, custom_code=custom_code)
    assert created is True
    assert url_record.short_code == custom_code

    # Verify duplicates on custom code raise error
    with pytest.raises(ValueError, match="Custom code already in use"):
        await service.shorten_url("https://another.com", custom_code=custom_code)

@pytest.mark.asyncio
async def test_resolve_url_success(db_session, mock_redis):
    repo = URLRepository(db_session)
    service = URLService(repo, mock_redis)
    
    # Set cache directly
    await mock_redis.set("code:xyz", "https://cached-url.com")
    
    resolved = await service.resolve_url("xyz")
    assert resolved == "https://cached-url.com"

@pytest.mark.asyncio
async def test_resolve_url_not_found(db_session, mock_redis):
    repo = URLRepository(db_session)
    service = URLService(repo, mock_redis)
    
    with pytest.raises(KeyError, match="Short code not found"):
        await service.resolve_url("nonexistent")

@pytest.mark.asyncio
async def test_record_click_analytics(db_session, mock_redis):
    repo = URLRepository(db_session)
    service = URLService(repo, mock_redis)
    
    # Setup url
    url_record = URL(id=123, original_url="https://analytics-test.com", short_code="an1")
    await repo.create(url_record)
    await db_session.commit()
    
    await service.record_click("an1", "https://google.com", "Mozilla/5.0")
    
    # Reload and check
    updated = await repo.get(123)
    await db_session.refresh(updated)
    assert updated.clicks == 1
    assert len(updated.analytics) == 1
    assert updated.analytics[0].referrer == "https://google.com"
    assert updated.analytics[0].user_agent == "Mozilla/5.0"

@pytest.mark.asyncio
async def test_base_repository_get_all_and_delete(db_session):
    repo = URLRepository(db_session)
    u1 = URL(original_url="https://r1.com", short_code="r1")
    u2 = URL(original_url="https://r2.com", short_code="r2")
    await repo.create(u1)
    await repo.create(u2)
    await db_session.commit()
    
    all_urls = await repo.get_all()
    assert len(all_urls) >= 2
    
    deleted = await repo.delete(u1.id)
    assert deleted is True
    
    all_urls_after = await repo.get_all()
    assert len(all_urls_after) == len(all_urls) - 1
    
    deleted_nonexistent = await repo.delete(99999)
    assert deleted_nonexistent is False

@pytest.mark.asyncio
async def test_url_service_fallback_counter_initialization(db_session, mock_redis):
    repo = URLRepository(db_session)
    service = URLService(repo, mock_redis)
    
    if "url_id_counter" in mock_redis.store:
        del mock_redis.store["url_id_counter"]
        
    existing = URL(id=15000000, original_url="https://seeded.com", short_code="seed")
    await repo.create(existing)
    await db_session.commit()
    
    url_rec, _ = await service.shorten_url("https://new-fallback.com")
    assert url_rec.id == 15000001

@pytest.mark.asyncio
async def test_redis_manager_lifecycle(mocker):
    mock_redis_inst = mocker.MagicMock()
    mock_redis_inst.close = mocker.AsyncMock()
    mocker.patch("redis.asyncio.from_url", return_value=mock_redis_inst)
    
    from app.redis import RedisManager
    manager = RedisManager()
    manager.initialize()
    assert manager.redis is not None
    await manager.close()

