"""Tests for collector utility functions."""
import pytest
from unittest.mock import AsyncMock, patch
from backend.app.services.collector import async_retry, CircuitBreaker, interval_manager


@pytest.mark.asyncio
async def test_async_retry_success_first_try():
    mock = AsyncMock(return_value="ok")
    result = await async_retry(mock)
    assert result == "ok"
    assert mock.call_count == 1


@pytest.mark.asyncio
async def test_async_retry_success_after_retry():
    call_count = 0
    
    async def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("temporary error")
        return "ok"
    
    result = await async_retry(flaky, max_retries=5, base_delay=0.01)
    assert result == "ok"
    assert call_count == 3


@pytest.mark.asyncio
async def test_async_retry_exhausted():
    async def always_fails():
        raise ValueError("persistent error")
    
    with pytest.raises(ValueError, match="persistent error"):
        await async_retry(always_fails, max_retries=2, base_delay=0.01)


@pytest.mark.asyncio
async def test_interval_manager_get_default():
    result = interval_manager.get("nonexistent_exchange", "BTCUSDT")
    assert result == 8


@pytest.mark.asyncio
async def test_interval_manager_get_binance_empty():
    result = interval_manager.get("binance", "UNKNOWN_SYMBOL")
    assert result == 8


@pytest.mark.asyncio
async def test_interval_manager_get_normalized():
    result = interval_manager.get("okx", "BTC-USDT")
    assert result == 8  # default since no intervals loaded


@pytest.mark.asyncio
async def test_interval_manager_refresh():
    await interval_manager.refresh()
    assert "binance" in interval_manager.intervals
