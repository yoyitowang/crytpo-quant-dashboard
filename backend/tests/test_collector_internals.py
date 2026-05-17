"""Tests for collector DataCollector internals."""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock, PropertyMock
from datetime import datetime, timezone, timedelta
from backend.app.services.collector import DataCollector, interval_manager


@pytest.mark.asyncio
async def test_notify_callbacks_filters_expired():
    dc = DataCollector()
    expired_item = {
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "rate": 0.0001,
        "settlement_time": datetime.now(timezone.utc) - timedelta(hours=1),
    }
    await dc._notify_callbacks(expired_item)
    assert dc.queue.qsize() == 0


@pytest.mark.asyncio
async def test_notify_callbacks_accepts_fresh():
    dc = DataCollector()
    fresh_item = {
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "rate": 0.0001,
        "settlement_time": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    await dc._notify_callbacks(fresh_item)
    assert dc.queue.qsize() == 1


@pytest.mark.asyncio
async def test_notify_callbacks_list():
    dc = DataCollector()
    items = [
        {
            "exchange": "binance",
            "symbol": "BTCUSDT",
            "rate": 0.0001,
            "settlement_time": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        {
            "exchange": "okx",
            "symbol": "ETHUSDT",
            "rate": -0.0002,
            "settlement_time": datetime.now(timezone.utc) + timedelta(hours=1),
        },
    ]
    await dc._notify_callbacks(items)
    assert dc.queue.qsize() == 1  # one list item containing 2 items


@pytest.mark.asyncio
async def test_notify_callbacks_all_filtered():
    dc = DataCollector()
    items = [
        {
            "exchange": "binance",
            "symbol": "BTCUSDT",
            "rate": 0.0001,
            "settlement_time": datetime.now(timezone.utc) - timedelta(hours=1),
        },
    ]
    await dc._notify_callbacks(items)
    assert dc.queue.qsize() == 0


@pytest.mark.asyncio
async def test_notify_callbacks_adds_interval():
    dc = DataCollector()
    item = {
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "rate": 0.0001,
        "settlement_time": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    await dc._notify_callbacks(item)
    msg = dc.queue.get_nowait()
    assert msg.get("interval") == 8


@pytest.mark.asyncio
async def test_notify_callbacks_handles_missing_settlement():
    dc = DataCollector()
    item = {
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "rate": 0.0001,
    }
    await dc._notify_callbacks(item)
    assert dc.queue.qsize() == 1


def test_get_circuit_states():
    dc = DataCollector()
    states = dc.get_circuit_states()
    assert "binance" in states
    assert states["binance"] == "closed"


def test_interval_manager_get_with_existing():
    interval_manager.intervals["testex"] = {"BTCUSDT": 8, "ETHUSDT": 4}
    result = interval_manager.get("testex", "BTCUSDT")
    assert result == 8


def test_interval_manager_get_with_normalization():
    interval_manager.intervals["testex"] = {"BTCUSDT": 8}
    result = interval_manager.get("testex", "BTC-USDT")
    assert result == 8


def test_interval_manager_get_fallback_default():
    interval_manager.intervals["testex"] = {}
    result = interval_manager.get("testex", "NONEXISTENT")
    assert result == 8


def test_interval_manager_get_binance_clean():
    interval_manager.intervals["binance"] = {"BTCUSDT": 4}
    result = interval_manager.get("binance", "BTC-USDT")
    assert result == 4


def test_exchange_routing():
    dc = DataCollector()
    assert "binance" in dc.exchanges
    assert "okx" in dc.exchanges
    assert "bybit" in dc.exchanges
    assert "bitget" in dc.exchanges
    assert "gate" in dc.exchanges
    assert "kucoin" in dc.exchanges
    assert "coinw" in dc.exchanges
    assert "mexc" in dc.exchanges
    assert "bingx" in dc.exchanges
    assert "aden" in dc.exchanges
    assert "hyperliquid" in dc.exchanges
    assert "asterdex" in dc.exchanges
    assert "lighter" in dc.exchanges


def test_circuit_breakers_per_exchange():
    dc = DataCollector()
    for name in dc.exchanges:
        assert name in dc.circuit_breakers
        assert dc.circuit_breakers[name].state == "closed"


def test_register_callback():
    dc = DataCollector()
    cb = lambda x: x
    dc.register_callback(cb)
    assert cb in dc.callbacks


@pytest.mark.asyncio
async def test_notify_callbacks_queue_full_handled():
    dc = DataCollector()
    dc.queue = asyncio.Queue(maxsize=1)
    await dc.queue.put("placeholder")

    fresh = {
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "rate": 0.0001,
        "settlement_time": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    await dc._notify_callbacks(fresh)
    # After QueueFull, should remove oldest item and insert new one
    assert dc.queue.qsize() == 1
    msg = dc.queue.get_nowait()
    assert msg["symbol"] == "BTCUSDT"
