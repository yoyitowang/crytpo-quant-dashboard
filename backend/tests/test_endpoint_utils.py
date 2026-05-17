"""Tests for utility functions in endpoints."""
from backend.app.api.endpoints import get_history_from_db


def test_get_history_from_db_empty_for_unknown():
    """get_history_from_db returns empty list when no DB session available."""
    import asyncio
    res = asyncio.run(get_history_from_db("test_exchange", "BTCUSDT", 7))
    assert res == []
