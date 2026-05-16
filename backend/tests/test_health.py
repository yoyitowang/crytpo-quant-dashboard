import pytest
from httpx import AsyncClient, ASGITransport
from backend.app.main import app


@pytest.mark.asyncio
async def test_root_returns_active():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "Active"


@pytest.mark.asyncio
async def test_health_live_returns_200():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health/live")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_compressed_rates_returns_list():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/rates/compressed")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
