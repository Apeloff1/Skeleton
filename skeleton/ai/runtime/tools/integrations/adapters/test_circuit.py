"""Tests for the circuit breaker state machine and breaker board."""

from __future__ import annotations

import pytest

from .circuit import BreakerBoard, CircuitBreaker, CircuitBreakerConfig, CircuitState
from .deadline import ManualClock
from .errors import (
    AuthenticationError,
    CapabilityDeniedError,
    CircuitOpenError,
    InvalidRequestError,
    OperationCancelledError,
    ProviderUnavailableError,
)


def make(clock: ManualClock | None = None, **kw) -> CircuitBreaker:
    cfg = CircuitBreakerConfig(**{"failure_threshold": 3, "reset_timeout": 10, "min_calls": 100, **kw})
    return CircuitBreaker("p", cfg, clock=clock or ManualClock())


def test_config_validation():
    with pytest.raises(ValueError):
        CircuitBreakerConfig(failure_threshold=0)
    with pytest.raises(ValueError):
        CircuitBreakerConfig(success_threshold=3, half_open_max_calls=2)
    with pytest.raises(ValueError):
        CircuitBreakerConfig(failure_rate=0)
    with pytest.raises(ValueError):
        CircuitBreakerConfig.from_dict({"nope": 1})
    assert CircuitBreakerConfig.from_dict({"failure_threshold": 2}).failure_threshold == 2


def test_trips_after_consecutive_failures_and_fails_fast():
    br = make()
    for _ in range(2):
        br.acquire()
        br.record_failure(ProviderUnavailableError())
    assert br.state is CircuitState.CLOSED
    br.acquire()
    br.record_failure(ProviderUnavailableError())
    assert br.state is CircuitState.OPEN
    with pytest.raises(CircuitOpenError) as info:
        br.acquire()
    assert info.value.reopen_in == 10
    assert br.trips == 1


def test_success_resets_consecutive_count():
    br = make()
    br.record_failure(ProviderUnavailableError())
    br.record_failure(ProviderUnavailableError())
    br.record_success()
    br.record_failure(ProviderUnavailableError())
    assert br.state is CircuitState.CLOSED


def test_neutral_errors_do_not_count():
    br = make(failure_threshold=1)
    for err in (InvalidRequestError(), OperationCancelledError(), CapabilityDeniedError()):
        br.record_failure(err)
    assert br.state is CircuitState.CLOSED
    br.record_failure(AuthenticationError())
    assert br.state is CircuitState.OPEN


def test_half_open_probe_closes_on_success():
    clock = ManualClock()
    transitions: list[tuple[str, str]] = []
    br = CircuitBreaker(
        "p",
        CircuitBreakerConfig(failure_threshold=1, reset_timeout=5),
        clock=clock,
        on_transition=lambda _n, a, b: transitions.append((a.value, b.value)),
    )
    br.record_failure()
    clock.advance(5)
    assert br.state is CircuitState.HALF_OPEN
    assert br.allow()
    assert not br.allow()  # only one probe
    br.record_success()
    assert br.state is CircuitState.CLOSED
    assert transitions == [("closed", "open"), ("open", "half_open"), ("half_open", "closed")]


def test_half_open_failure_reopens():
    clock = ManualClock()
    br = make(clock, failure_threshold=1, reset_timeout=5)
    br.record_failure()
    clock.advance(6)
    assert br.allow()
    br.record_failure(ProviderUnavailableError())
    assert br.state is CircuitState.OPEN
    assert br.trips == 2


def test_half_open_release_returns_slot():
    clock = ManualClock()
    br = make(clock, failure_threshold=1, reset_timeout=1)
    br.record_failure()
    clock.advance(1)
    assert br.allow()
    br.record_failure(OperationCancelledError())  # neutral -> slot released
    assert br.state is CircuitState.HALF_OPEN
    assert br.allow()


def test_failure_rate_window_trips():
    br = CircuitBreaker(
        "p",
        CircuitBreakerConfig(failure_threshold=100, window_size=10, min_calls=4, failure_rate=0.5),
        clock=ManualClock(),
    )
    br.record_success()
    br.record_failure()
    br.record_success()
    assert br.state is CircuitState.CLOSED
    br.record_failure()
    assert br.state is CircuitState.OPEN


def test_force_open_reset_and_snapshot():
    br = make()
    br.force_open()
    snap = br.snapshot()
    assert snap["state"] == "open" and snap["trips"] == 1
    br.reset()
    assert br.state is CircuitState.CLOSED
    assert br.reopen_in() == 0.0


def test_observer_errors_are_swallowed():
    def bad(*_a):
        raise RuntimeError("observer bug")

    br = CircuitBreaker("p", CircuitBreakerConfig(failure_threshold=1), clock=ManualClock(), on_transition=bad)
    br.record_failure()
    assert br.state is CircuitState.OPEN


def test_breaker_board_overrides_and_listing():
    clock = ManualClock()
    board = BreakerBoard(
        CircuitBreakerConfig(failure_threshold=5),
        clock=clock,
        overrides={"fragile": CircuitBreakerConfig(failure_threshold=1)},
    )
    assert board.get("a") is board.get("a")
    board.get("fragile").record_failure()
    board.get("a").record_failure()
    assert board.open_providers() == ["fragile"]
    assert set(board.snapshot()) == {"a", "fragile"}
