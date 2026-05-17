"""Tests for collector _safe_handler and _worker."""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from backend.app.services.collector import DataCollector


class _StopTest(Exception):
    pass


async def _stop_after(n):
    """Raise _StopTest after n calls."""
    calls = 0
    async def _inner(*a, **kw):
        nonlocal calls
        calls += 1
        if calls >= n:
            raise _StopTest
    return _inner


@pytest.mark.asyncio
async def test_safe_handler_success():
    dc = DataCollector()
    handler = AsyncMock()
    handler.side_effect = _StopTest
    sleep_fn = await _stop_after(2)

    with patch("asyncio.sleep", sleep_fn):
        with pytest.raises(_StopTest):
            await dc._safe_handler("binance", handler)

    assert handler.awaited





@pytest.mark.asyncio
async def test_safe_handler_circuit_opens():
    dc = DataCollector()
    handler = AsyncMock(side_effect=ValueError("fail"))
    cb = dc.circuit_breakers["binance"]
    cb.failure_threshold = 2
    cb.open_duration = 99999
    sleep_fn = await _stop_after(4)

    with patch("asyncio.sleep", sleep_fn):
        with pytest.raises(_StopTest):
            await dc._safe_handler("binance", handler)

    assert cb.failures >= 2
    assert cb.state == "open"


@pytest.mark.asyncio
async def test_safe_handler_skips_when_open():
    dc = DataCollector()
    cb = dc.circuit_breakers["binance"]
    cb._state = "open"
    cb._last_failure_time = 9999999999
    handler = AsyncMock()
    sleep_fn = await _stop_after(1)

    with patch("asyncio.sleep", sleep_fn):
        with pytest.raises(_StopTest):
            await dc._safe_handler("binance", handler)

    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_worker_processes_item():
    dc = DataCollector()
    results = []

    def sync_cb(data):
        results.append(data)

    dc.register_callback(sync_cb)

    await dc.queue.put({
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "rate": 0.0001,
        "interval": 8,
    })

    task = asyncio.create_task(dc._worker())
    await asyncio.sleep(0.3)
    task.cancel()

    assert len(results) >= 1
    key = "latest:binance:BTCUSDT"
    assert key in dc.latest_rates


@pytest.mark.asyncio
async def test_worker_handles_malformed_item():
    dc = DataCollector()

    await dc.queue.put("not_a_dict")

    task = asyncio.create_task(dc._worker())
    await asyncio.sleep(0.3)
    task.cancel()

    assert dc.queue.qsize() == 0


@pytest.mark.asyncio
async def test_worker_processes_list_item():
    dc = DataCollector()
    results = []

    def sync_cb(data):
        results.append(data)

    dc.register_callback(sync_cb)

    await dc.queue.put([
        {"exchange": "binance", "symbol": "BTCUSDT", "rate": 0.0001, "interval": 8},
        {"exchange": "okx", "symbol": "ETHUSDT", "rate": -0.0002, "interval": 8},
    ])

    task = asyncio.create_task(dc._worker())
    await asyncio.sleep(0.3)
    task.cancel()

    assert len(results) >= 2
