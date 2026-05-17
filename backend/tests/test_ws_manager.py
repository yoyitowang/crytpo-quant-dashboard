"""Tests for WebSocket manager."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from backend.app.services.websocket_manager import ConnectionManager as WebSocketManager


@pytest.mark.asyncio
async def test_ws_manager_initial_state():
    wsm = WebSocketManager()
    assert len(wsm.active_connections) == 0


@pytest.mark.asyncio
async def test_ws_connect():
    wsm = WebSocketManager()
    mock_ws = AsyncMock()
    mock_ws.headers = {}
    
    await wsm.connect(mock_ws)
    assert len(wsm.active_connections) == 1
    assert mock_ws in wsm.active_connections
    assert mock_ws.accept.called


@pytest.mark.asyncio
async def test_ws_disconnect():
    wsm = WebSocketManager()
    mock_ws = AsyncMock()
    mock_ws.headers = {}
    
    await wsm.connect(mock_ws)
    assert len(wsm.active_connections) == 1
    
    wsm.disconnect(mock_ws)  # not async
    assert len(wsm.active_connections) == 0


@pytest.mark.asyncio
async def test_broadcast_with_no_connections():
    wsm = WebSocketManager()
    await wsm.broadcast({"test": "data"})
    # should not crash


@pytest.mark.asyncio
async def test_broadcast_enqueues_message():
    wsm = WebSocketManager()
    mock_ws = AsyncMock()
    mock_ws.headers = {}
    
    await wsm.connect(mock_ws)
    await wsm.broadcast({"test": "data"})
    
    assert len(wsm.batch_queue) > 0


@pytest.mark.asyncio
async def test_heartbeat_loop_not_started_without_connect():
    wsm = WebSocketManager()
    assert wsm._heartbeat_task is None


@pytest.mark.asyncio
async def test_send_batch_sends_to_connections():
    wsm = WebSocketManager()
    mock_ws = AsyncMock()
    mock_ws.headers = {}

    await wsm.connect(mock_ws)
    await wsm._send_batch([{"test": "data"}])

    mock_ws.send_text.assert_called_once()


@pytest.mark.asyncio
async def test_send_batch_removes_stale():
    wsm = WebSocketManager()
    bad_ws = AsyncMock()
    bad_ws.headers = {}
    bad_ws.send_text = AsyncMock(side_effect=Exception("gone"))

    await wsm.connect(bad_ws)
    await wsm._send_batch([{"test": "data"}])

    assert len(wsm.active_connections) == 0
