"""Circuit breaker for repeatedly failing logical commands."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import threading
import time
from typing import Callable

from skeleton.shells.errors import CircuitOpen, ShellErrorCode, ShellErrorContext


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True)
class CircuitPolicy:
    failure_threshold: int = 5
    recovery_seconds: float = 30.0
    half_open_successes: int = 1

    def __post_init__(self) -> None:
        if self.failure_threshold <= 0 or self.half_open_successes <= 0:
            raise ValueError("circuit thresholds must be positive")
        if self.recovery_seconds < 0:
            raise ValueError("recovery_seconds must be non-negative")


@dataclass(frozen=True)
class CircuitSnapshot:
    state: CircuitState
    failures: int
    half_open_successes: int
    opened_at: float | None


class CircuitBreaker:
    def __init__(
        self,
        policy: CircuitPolicy | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.policy = policy or CircuitPolicy()
        self._clock = clock
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._half_open_successes = 0
        self._opened_at: float | None = None
        self._lock = threading.RLock()

    def _refresh(self) -> None:
        if self._state is not CircuitState.OPEN or self._opened_at is None:
            return
        if self._clock() - self._opened_at >= self.policy.recovery_seconds:
            self._state = CircuitState.HALF_OPEN
            self._half_open_successes = 0

    def state(self) -> CircuitState:
        with self._lock:
            self._refresh()
            return self._state

    def allow(self, *, command: str | None = None) -> None:
        with self._lock:
            self._refresh()
            if self._state is CircuitState.OPEN:
                raise CircuitOpen(
                    ShellErrorContext(
                        ShellErrorCode.CIRCUIT_OPEN,
                        command=command,
                        detail="circuit is open",
                    )
                )

    def record_success(self) -> None:
        with self._lock:
            self._refresh()
            if self._state is CircuitState.HALF_OPEN:
                self._half_open_successes += 1
                if self._half_open_successes >= self.policy.half_open_successes:
                    self._state = CircuitState.CLOSED
                    self._failures = 0
                    self._opened_at = None
                    self._half_open_successes = 0
                return
            if self._state is CircuitState.CLOSED:
                self._failures = 0

    def record_failure(self) -> None:
        with self._lock:
            self._refresh()
            if self._state is CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._opened_at = self._clock()
                self._half_open_successes = 0
                return
            if self._state is CircuitState.CLOSED:
                self._failures += 1
                if self._failures >= self.policy.failure_threshold:
                    self._state = CircuitState.OPEN
                    self._opened_at = self._clock()

    def reset(self) -> None:
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failures = 0
            self._half_open_successes = 0
            self._opened_at = None

    def snapshot(self) -> CircuitSnapshot:
        with self._lock:
            self._refresh()
            return CircuitSnapshot(
                self._state,
                self._failures,
                self._half_open_successes,
                self._opened_at,
            )


class CircuitRegistry:
    def __init__(self, default_policy: CircuitPolicy | None = None) -> None:
        self.default_policy = default_policy or CircuitPolicy()
        self._circuits: dict[str, CircuitBreaker] = {}
        self._lock = threading.RLock()

    def get(self, key: str) -> CircuitBreaker:
        with self._lock:
            breaker = self._circuits.get(key)
            if breaker is None:
                breaker = CircuitBreaker(self.default_policy)
                self._circuits[key] = breaker
            return breaker

    def snapshot(self) -> dict[str, CircuitSnapshot]:
        with self._lock:
            return {key: breaker.snapshot() for key, breaker in self._circuits.items()}

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                for breaker in self._circuits.values():
                    breaker.reset()
            elif key in self._circuits:
                self._circuits[key].reset()
