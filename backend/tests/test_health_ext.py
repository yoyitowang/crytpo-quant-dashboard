"""Tests for health and analysis endpoints."""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from httpx import AsyncClient, ASGITransport
from backend.app.main import app
from backend.app.dependencies import set_redis


@pytest.fixture
def mock_redis():
    mock = AsyncMock()
    mock.ping = AsyncMock(return_value=True)
    mock.keys = AsyncMock(return_value=["latest:binance:btcusdt"])
    mock.mget = AsyncMock(return_value=['{"exchange": "binance", "symbol": "BTCUSDT", "rate": 0.0001, "timestamp": "2026-05-16T12:00:00+00:00"}'])
    return mock


@pytest.fixture
def client(mock_redis):
    set_redis(mock_redis)
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_root_returns_active(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    assert resp.json() == {"message": "Active"}


@pytest.mark.asyncio
async def test_health_live(client):
    resp = await client.get("/api/health/live")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_health_ready(client):
    resp = await client.get("/api/health/ready")
    assert resp.status_code in (200, 503)
    data = resp.json()
    assert "status" in data
    assert "circuit_breakers" in data


@pytest.mark.asyncio
async def test_compressed_rates_returns_list(client):
    resp = await client.get("/api/rates/compressed")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_latest_rates(client):
    resp = await client.get("/api/rates/latest")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_summary(client):
    resp = await client.get("/api/analysis/summary")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_metrics_endpoint(client):
    resp = await client.get("/api/metrics")
    assert resp.status_code == 200
