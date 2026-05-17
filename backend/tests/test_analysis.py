"""Tests for analysis endpoints."""
import pytest
from httpx import AsyncClient, ASGITransport
from backend.app.main import app


@pytest.mark.asyncio
async def test_spreads_returns_list():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/analysis/spreads")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_orderbook_returns_error_for_unknown_exchange():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/orderbook/unknown_exchange/BTCUSDT")
    assert resp.status_code == 200
    data = resp.json()
    assert "error" in data


@pytest.mark.asyncio
async def test_orderbook_returns_dict_for_valid_exchange():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/orderbook/binance/BTCUSDT")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_orderbook_with_slippage():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/orderbook/binance/BTCUSDT?buy_size=1000&sell_size=500")
    assert resp.status_code == 200
