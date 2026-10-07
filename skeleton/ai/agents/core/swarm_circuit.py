"""Circuit breaker policy for isolating repeatedly failing swarm workers."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from threading import RLock
from time import monotonic
from typing import Callable


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(slots=True)
class Circuit:
    state: CircuitState = CircuitState.CLOSED
    failures: int = 0
    opened_at: float | None = None
    probes: int = 0
    probe_in_flight: bool = False


class CircuitBreaker:
    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        recovery_seconds: float = 30,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if failure_threshold < 1 or recovery_seconds <= 0:
            raise ValueError("invalid circuit breaker configuration")
        self.failure_threshold = failure_threshold
        self.recovery_seconds = recovery_seconds
        self.clock = clock
        self._circuits: dict[str, Circuit] = {}
        self._lock = RLock()

    def circuit(self, key: str) -> Circuit:
        with self._lock:
            return self._circuits.setdefault(key, Circuit())

    def allow(self, key: str) -> bool:
        with self._lock:
            c = self._circuits.setdefault(key, Circuit())
            if c.state is CircuitState.OPEN:
                if c.opened_at is None or self.clock() - c.opened_at < self.recovery_seconds:
                    return False
                c.state = CircuitState.HALF_OPEN
                c.probe_in_flight = False
            if c.state is CircuitState.HALF_OPEN:
                if c.probe_in_flight:
                    return False
                c.probe_in_flight = True
                c.probes += 1
                return True
            return True

    def success(self, key: str) -> Circuit:
        with self._lock:
            c = self._circuits.setdefault(key, Circuit())
            c.state = CircuitState.CLOSED
            c.failures = 0
            c.opened_at = None
            c.probe_in_flight = False
            return c

    def failure(self, key: str) -> Circuit:
        with self._lock:
            c = self._circuits.setdefault(key, Circuit())
            c.failures += 1
            if c.state is CircuitState.HALF_OPEN or c.failures >= self.failure_threshold:
                c.state = CircuitState.OPEN
                c.opened_at = self.clock()
                c.probe_in_flight = False
            return c

    def snapshot(self) -> dict[str, dict[str, object]]:
        with self._lock:
            return {
                key: {
                    "state": value.state.value,
                    "failures": value.failures,
                    "opened_at": value.opened_at,
                    "probes": value.probes,
                    "probe_in_flight": value.probe_in_flight,
                }
                for key, value in sorted(self._circuits.items())
            }
