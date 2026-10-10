"""Per-provider circuit breaker (closed → open → half-open → closed).

The breaker trips after ``failure_threshold`` consecutive counted failures or
when the failure rate over a sliding window exceeds ``failure_rate`` with at
least ``min_calls`` samples.  While open, calls fail fast with
:class:`CircuitOpenError` until ``reset_timeout`` elapses; then a bounded
number of half-open probes decide whether to close or re-open.  Only failures
that indicate provider health count: caller mistakes (invalid request,
cancellation, capability denial) never trip the breaker.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from .deadline import Clock, MonotonicClock
from .errors import (
    CapabilityDeniedError,
    CircuitOpenError,
    InvalidRequestError,
    OperationCancelledError,
)

__all__ = ["CircuitState", "CircuitBreakerConfig", "CircuitBreaker", "BreakerBoard"]


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True)
class CircuitBreakerConfig:
    failure_threshold: int = 5
    reset_timeout: float = 30.0
    half_open_max_calls: int = 1
    success_threshold: int = 1
    window_size: int = 20
    failure_rate: float = 0.5
    min_calls: int = 10

    def __post_init__(self) -> None:
        if self.failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if self.reset_timeout < 0:
            raise ValueError("reset_timeout must be >= 0")
        if self.half_open_max_calls < 1 or self.success_threshold < 1:
            raise ValueError("half-open limits must be >= 1")
        if self.success_threshold > self.half_open_max_calls:
            raise ValueError("success_threshold cannot exceed half_open_max_calls")
        if self.window_size < 1 or self.min_calls < 1:
            raise ValueError("window_size and min_calls must be >= 1")
        if not 0.0 < self.failure_rate <= 1.0:
            raise ValueError("failure_rate must be within (0, 1]")

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CircuitBreakerConfig":
        allowed = set(cls.__dataclass_fields__)
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"unknown circuit breaker keys: {sorted(unknown)}")
        return cls(**payload)


_NEUTRAL = (InvalidRequestError, OperationCancelledError, CapabilityDeniedError)


def counts_as_failure(error: BaseException) -> bool:
    """Caller mistakes and policy refusals say nothing about provider health."""

    return not isinstance(error, _NEUTRAL)


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        config: CircuitBreakerConfig | None = None,
        *,
        clock: Clock | None = None,
        on_transition: Callable[[str, CircuitState, CircuitState], None] | None = None,
    ) -> None:
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._clock = clock or MonotonicClock()
        self._on_transition = on_transition
        self._lock = threading.RLock()
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._opened_at = 0.0
        self._half_open_inflight = 0
        self._half_open_successes = 0
        self._window: deque[bool] = deque(maxlen=self.config.window_size)
        self.trips = 0

    # -- state -------------------------------------------------------------
    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._maybe_half_open()
            return self._state

    def _transition(self, new: CircuitState) -> None:
        old = self._state
        if old is new:
            return
        self._state = new
        if new is CircuitState.OPEN:
            self._opened_at = self._clock.now()
            self.trips += 1
        if new is CircuitState.HALF_OPEN:
            self._half_open_inflight = 0
            self._half_open_successes = 0
        if new is CircuitState.CLOSED:
            self._consecutive_failures = 0
            self._window.clear()
        if self._on_transition is not None:
            try:
                self._on_transition(self.name, old, new)
            except Exception:  # noqa: BLE001 - observers must not break the breaker
                pass

    def _maybe_half_open(self) -> None:
        if self._state is CircuitState.OPEN:
            if self._clock.now() - self._opened_at >= self.config.reset_timeout:
                self._transition(CircuitState.HALF_OPEN)

    def reopen_in(self) -> float:
        with self._lock:
            if self._state is not CircuitState.OPEN:
                return 0.0
            return max(0.0, self.config.reset_timeout - (self._clock.now() - self._opened_at))

    # -- call protocol -----------------------------------------------------
    def allow(self) -> bool:
        with self._lock:
            self._maybe_half_open()
            if self._state is CircuitState.CLOSED:
                return True
            if self._state is CircuitState.HALF_OPEN:
                if self._half_open_inflight < self.config.half_open_max_calls:
                    self._half_open_inflight += 1
                    return True
                return False
            return False

    def acquire(self) -> None:
        if not self.allow():
            raise CircuitOpenError(
                f"circuit for {self.name!r} is {self.state.value}",
                provider=self.name,
                reopen_in=self.reopen_in(),
            )

    def record_success(self) -> None:
        with self._lock:
            if self._state is CircuitState.HALF_OPEN:
                self._half_open_successes += 1
                if self._half_open_successes >= self.config.success_threshold:
                    self._transition(CircuitState.CLOSED)
                return
            self._consecutive_failures = 0
            self._window.append(True)

    def record_failure(self, error: BaseException | None = None) -> None:
        with self._lock:
            if error is not None and not counts_as_failure(error):
                self.release()
                return
            if self._state is CircuitState.HALF_OPEN:
                self._transition(CircuitState.OPEN)
                return
            if self._state is CircuitState.OPEN:
                return
            self._consecutive_failures += 1
            self._window.append(False)
            if self._consecutive_failures >= self.config.failure_threshold or self._rate_exceeded():
                self._transition(CircuitState.OPEN)

    def release(self) -> None:
        """Return a half-open slot without recording an outcome."""

        with self._lock:
            if self._state is CircuitState.HALF_OPEN and self._half_open_inflight > 0:
                self._half_open_inflight -= 1

    def _rate_exceeded(self) -> bool:
        samples = len(self._window)
        if samples < self.config.min_calls:
            return False
        failures = sum(1 for ok in self._window if not ok)
        return failures / samples >= self.config.failure_rate

    def reset(self) -> None:
        with self._lock:
            self._transition(CircuitState.CLOSED)

    def force_open(self) -> None:
        with self._lock:
            self._transition(CircuitState.OPEN)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            self._maybe_half_open()
            samples = len(self._window)
            failures = sum(1 for ok in self._window if not ok)
            return {
                "name": self.name,
                "state": self._state.value,
                "consecutive_failures": self._consecutive_failures,
                "window_samples": samples,
                "window_failure_rate": (failures / samples) if samples else 0.0,
                "trips": self.trips,
                "reopen_in": self.reopen_in(),
            }


class BreakerBoard:
    """Lazily creates and holds one breaker per provider name."""

    def __init__(
        self,
        default: CircuitBreakerConfig | None = None,
        *,
        clock: Clock | None = None,
        overrides: dict[str, CircuitBreakerConfig] | None = None,
        on_transition: Callable[[str, CircuitState, CircuitState], None] | None = None,
    ) -> None:
        self._default = default or CircuitBreakerConfig()
        self._clock = clock or MonotonicClock()
        self._overrides = dict(overrides or {})
        self._on_transition = on_transition
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()

    def get(self, name: str) -> CircuitBreaker:
        with self._lock:
            breaker = self._breakers.get(name)
            if breaker is None:
                breaker = CircuitBreaker(
                    name,
                    self._overrides.get(name, self._default),
                    clock=self._clock,
                    on_transition=self._on_transition,
                )
                self._breakers[name] = breaker
            return breaker

    def snapshot(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            names = sorted(self._breakers)
        return {name: self.get(name).snapshot() for name in names}

    def open_providers(self) -> list[str]:
        with self._lock:
            items = list(self._breakers.items())
        return sorted(name for name, br in items if br.state is CircuitState.OPEN)
