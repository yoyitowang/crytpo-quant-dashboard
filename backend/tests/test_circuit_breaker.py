"""Tests for CircuitBreaker."""
import time
from backend.app.services.collector import CircuitBreaker


def test_circuit_initial_state():
    cb = CircuitBreaker("test")
    assert cb.state == "closed"
    assert not cb.is_open
    assert cb.failures == 0


def test_circuit_opens_after_threshold():
    cb = CircuitBreaker("test", failure_threshold=3, open_duration=60)
    for _ in range(3):
        cb.record_failure()
    assert cb.state == "open"
    assert cb.is_open
    assert cb.failures == 3


def test_circuit_stays_closed_below_threshold():
    cb = CircuitBreaker("test", failure_threshold=5)
    for _ in range(3):
        cb.record_failure()
    assert cb.state == "closed"
    assert not cb.is_open


def test_circuit_resets_on_success():
    cb = CircuitBreaker("test", failure_threshold=3)
    for _ in range(3):
        cb.record_failure()
    assert cb.state == "open"
    cb.record_success()
    assert cb.state == "closed"
    assert not cb.is_open
    assert cb.failures == 0


def test_circuit_half_open_after_duration():
    cb = CircuitBreaker("test", failure_threshold=3, open_duration=0.1)
    for _ in range(3):
        cb.record_failure()
    assert cb.state == "open"
    time.sleep(0.15)
    assert not cb.is_open
    assert cb.state == "half_open"


def test_circuit_stays_open_within_duration():
    cb = CircuitBreaker("test", failure_threshold=3, open_duration=60)
    for _ in range(3):
        cb.record_failure()
    assert cb.is_open
    # Immediately check — should still be open
    assert cb.is_open
    assert cb.state == "open"
