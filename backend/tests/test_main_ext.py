"""Tests for main.py ws_callback and _metrics_loop."""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class _StopMetrics(Exception):
    pass


async def _break_after_two(*args, **kwargs):
    """Allow one sleep to complete, raise on the second."""
    if not hasattr(_break_after_two, "_count"):
        _break_after_two._count = 0
    _break_after_two._count += 1
    if _break_after_two._count >= 2:
        raise _StopMetrics


@pytest.mark.asyncio
async def test_ws_callback_broadcasts():
    from backend.app.main import ws_callback
    mock_ws_mgr = MagicMock()
    mock_ws_mgr.broadcast = AsyncMock()
    with patch("backend.app.main.ws_manager", mock_ws_mgr):
        await ws_callback({"test": "data"})
        mock_ws_mgr.broadcast.assert_awaited_once_with({"test": "data"})


@pytest.mark.asyncio
async def test_ws_callback_with_list():
    from backend.app.main import ws_callback
    mock_ws_mgr = MagicMock()
    mock_ws_mgr.broadcast = AsyncMock()
    items = [{"a": 1}, {"b": 2}]
    with patch("backend.app.main.ws_manager", mock_ws_mgr):
        await ws_callback(items)
        mock_ws_mgr.broadcast.assert_awaited_once_with(items)


@pytest.mark.asyncio
async def test_ws_callback_with_nested():
    from backend.app.main import ws_callback
    mock_ws_mgr = MagicMock()
    mock_ws_mgr.broadcast = AsyncMock()
    data = {"exchange": "binance", "symbol": "BTCUSDT", "rate": 0.0001}
    with patch("backend.app.main.ws_manager", mock_ws_mgr):
        await ws_callback(data)
        mock_ws_mgr.broadcast.assert_awaited_once_with(data)


@pytest.mark.asyncio
async def test_metrics_loop_updates():
    from backend.app.main import _metrics_loop
    _break_after_two._count = 0
    mock_ws_mgr = MagicMock()
    mock_ws_mgr.active_connections = [1, 2, 3]

    with (
        patch("backend.app.main.ws_manager", mock_ws_mgr),
        patch("backend.app.main.ws_active_connections") as mock_wsc,
        patch("backend.app.main.db_writer_queue_size") as mock_dbq,
        patch("backend.app.main.collector") as mock_collector,
        patch("backend.app.main.collector_circuit_open") as mock_cc,
        patch("asyncio.sleep", _break_after_two),
    ):
        mock_collector.circuit_breakers = {}

        with pytest.raises(_StopMetrics):
            await _metrics_loop()

        mock_wsc.set.assert_called_with(3)
        mock_dbq.set.assert_called()
