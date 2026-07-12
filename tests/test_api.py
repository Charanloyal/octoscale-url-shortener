import pytest
from fastapi import status

@pytest.mark.asyncio
async def test_shorten_endpoint_success(client):
    response = await client.post(
        "/api/v1/shorten",
        json={"original_url": "https://google.com"}
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["original_url"] == "https://google.com"
    assert "short_code" in data
    assert "short_url" in data

@pytest.mark.asyncio
async def test_shorten_endpoint_validation_error(client):
    # Invalid URL structure
    response = await client.post(
        "/api/v1/shorten",
        json={"original_url": "invalid-url-string"}
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

@pytest.mark.asyncio
async def test_shorten_endpoint_custom_code(client):
    response = await client.post(
        "/api/v1/shorten",
        json={"original_url": "https://yahoo.com", "custom_code": "yahoo"}
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["short_code"] == "yahoo"

    # Try duplicate custom code
    response2 = await client.post(
        "/api/v1/shorten",
        json={"original_url": "https://bing.com", "custom_code": "yahoo"}
    )
    assert response2.status_code == status.HTTP_400_BAD_REQUEST

@pytest.mark.asyncio
async def test_redirect_endpoint(client):
    # Shorten a URL first
    res = await client.post(
        "/api/v1/shorten",
        json={"original_url": "https://github.com", "custom_code": "gitredir"}
    )
    assert res.status_code == status.HTTP_201_CREATED

    # Hit redirect
    # Follow redirects = False to intercept the 307
    response = await client.get("/gitredir", headers={"referer": "https://t.co"})
    assert response.status_code == status.HTTP_307_TEMPORARY_REDIRECT
    assert response.headers["location"] == "https://github.com"

@pytest.mark.asyncio
async def test_analytics_endpoint(client):
    # Shorten
    await client.post(
        "/api/v1/shorten",
        json={"original_url": "https://netflix.com", "custom_code": "netflx"}
    )
    
    # Hit redirect to create click data
    await client.get("/netflx", headers={"user-agent": "Mozilla", "referer": "https://google.com"})

    # Fetch analytics
    response = await client.get("/api/v1/analytics/netflx")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["short_code"] == "netflx"
    assert data["original_url"] == "https://netflix.com"
    assert data["clicks"] == 1
    assert len(data["recent_clicks"]) == 1
    assert data["recent_clicks"][0]["referrer"] == "https://google.com"

@pytest.mark.asyncio
async def test_health_check_endpoint(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "healthy"
    assert data["components"]["database"] == "up"
    assert data["components"]["redis"] == "up"

@pytest.mark.asyncio
async def test_health_check_database_down(client, mocker):
    mocker.patch("sqlalchemy.ext.asyncio.AsyncSession.execute", side_effect=Exception("DB Down"))
    response = await client.get("/api/v1/health")
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    data = response.json()
    assert data["detail"]["status"] == "unhealthy"
    assert "down" in data["detail"]["components"]["database"]

@pytest.mark.asyncio
async def test_health_check_redis_down(client, mocker):
    mocker.patch("tests.conftest.MockRedis.ping", side_effect=Exception("Redis Down"))
    response = await client.get("/api/v1/health")
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    data = response.json()
    assert data["detail"]["status"] == "unhealthy"
    assert "down" in data["detail"]["components"]["redis"]

@pytest.mark.asyncio
async def test_rate_limiter_fail_open(client, mocker):
    mocker.patch("tests.conftest.MockRedis.pipeline", side_effect=Exception("Redis Pipeline Down"))
    response = await client.post(
        "/api/v1/shorten",
        json={"original_url": "https://google.com"}
    )
    assert response.status_code == status.HTTP_201_CREATED

@pytest.mark.asyncio
async def test_redirect_not_found_renders_html(client):
    response = await client.get("/nonexistentcode")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "text/html" in response.headers["content-type"]
    assert "Short URL code" in response.text
    assert "nonexistentcode" in response.text
    assert "does not exist." in response.text

