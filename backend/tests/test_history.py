"""Tests for history endpoints."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport
from backend.app.main import app
from backend.app.dependencies import set_redis


@pytest.mark.asyncio
async def test_history_returns_empty_for_unknown_exchange():
    """Should return empty list for exchanges without fetchFundingRateHistory."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/rates/history/unknown_exchange/BTCUSDT?days=7")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_history_all_returns_dict():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/rates/history_all/BTCUSDT?days=7")
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data


@pytest.mark.asyncio
async def test_history_coinw_returns_list():
    """Coinw should return a list (may be empty or contain data)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/rates/history/coinw/BTCUSDT?days=7")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_history_lighter_returns_list():
    """Lighter should return a list via official API (may be empty if API unavailable)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/rates/history/lighter/BTCUSDT?days=7")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
