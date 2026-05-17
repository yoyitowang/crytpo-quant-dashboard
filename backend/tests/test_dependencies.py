"""Tests for dependencies module."""
import pytest
from backend.app.dependencies import get_redis, set_redis


def test_get_redis_returns_none_by_default():
    assert get_redis() is None


def test_set_redis_and_get_redis():
    set_redis("mock_redis")
    assert get_redis() == "mock_redis"
    set_redis(None)
    assert get_redis() is None


def test_set_redis_none_clears():
    set_redis("mock")
    set_redis(None)
    assert get_redis() is None
