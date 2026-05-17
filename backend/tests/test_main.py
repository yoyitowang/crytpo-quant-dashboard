"""Tests for main.py core functions."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone
from backend.app.dependencies import set_redis


@pytest.mark.asyncio
async def test_db_callback_no_redis():
    """db_callback should do nothing when redis is None."""
    set_redis(None)
    from backend.app.main import db_callback
    # Should not raise
    await db_callback({"exchange": "test", "symbol": "BTCUSDT", "rate": 0.0001})
    # No assertions needed - just checking it doesn't crash


@pytest.mark.asyncio
async def test_db_callback_with_redis():
    """db_callback should store data in redis."""
    mock_redis = AsyncMock()
    set_redis(mock_redis)
    
    from backend.app.main import db_callback
    await db_callback({"exchange": "binance", "symbol": "BTCUSDT", "rate": 0.0001})
    
    assert mock_redis.mset.called


@pytest.mark.asyncio
async def test_db_callback_with_list():
    """db_callback should handle list of items."""
    mock_redis = AsyncMock()
    set_redis(mock_redis)
    
    from backend.app.main import db_callback
    items = [
        {"exchange": "binance", "symbol": "BTCUSDT", "rate": 0.0001},
        {"exchange": "okx", "symbol": "ETHUSDT", "rate": -0.0002},
    ]
    await db_callback(items)
    assert mock_redis.mset.called


@pytest.mark.asyncio
async def test_db_callback_with_settlement_time():
    """db_callback should handle datetime settlement_time."""
    mock_redis = AsyncMock()
    set_redis(mock_redis)
    
    from backend.app.main import db_callback
    await db_callback({
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "rate": 0.0001,
        "settlement_time": datetime.now(timezone.utc)
    })
    assert mock_redis.mset.called


@pytest.mark.asyncio
async def test_db_callback_with_interval():
    """db_callback should pass interval data."""
    mock_redis = AsyncMock()
    set_redis(mock_redis)
    
    from backend.app.main import db_callback
    await db_callback({
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "rate": 0.0001,
        "interval": 8
    })
    assert mock_redis.mset.called
