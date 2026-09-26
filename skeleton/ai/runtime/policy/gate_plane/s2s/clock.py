"""Injectable clocks for the Pack F service-to-service plane.

Every time-dependent decision in ``skeleton.gate_plane.s2s`` and
``skeleton.gate_plane.pipeline`` reads time through a :class:`Clock` so the
test and chaos suites can drive rotation windows, token expiry, breaker
cool-downs and retry backoff deterministically without real sleeps.
"""

from __future__ import annotations

import threading
import time
from typing import List, Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    """Minimal clock contract: wall time, monotonic time, and sleep."""

    def now(self) -> float:
        """Wall-clock seconds since the epoch (used for token iat/exp)."""

    def monotonic(self) -> float:
        """Monotonic seconds (used for deadlines, windows, cool-downs)."""

    def sleep(self, seconds: float) -> None:
        """Block (or virtually advance) for ``seconds``."""


class SystemClock:
    """Production clock backed by :mod:`time`."""

    def now(self) -> float:
        return time.time()

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            time.sleep(seconds)


class ManualClock:
    """Deterministic virtual clock.

    ``sleep`` advances virtual time instead of blocking, and every sleep is
    recorded so tests can assert on backoff schedules.
    """

    def __init__(self, start: float = 1_700_000_000.0, monotonic_start: float = 1_000.0) -> None:
        self._wall = float(start)
        self._mono = float(monotonic_start)
        self._lock = threading.Lock()
        self.sleeps: List[float] = []

    def now(self) -> float:
        with self._lock:
            return self._wall

    def monotonic(self) -> float:
        with self._lock:
            return self._mono

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("ManualClock cannot go backwards via advance(); use set_wall()")
        with self._lock:
            self._wall += seconds
            self._mono += seconds

    def set_wall(self, value: float) -> None:
        """Jump wall time only (models NTP skew); monotonic time is untouched."""
        with self._lock:
            self._wall = float(value)

    def sleep(self, seconds: float) -> None:
        seconds = max(0.0, float(seconds))
        self.sleeps.append(seconds)
        self.advance(seconds)


_SYSTEM = SystemClock()


def system_clock() -> SystemClock:
    return _SYSTEM


__all__ = ["Clock", "ManualClock", "SystemClock", "system_clock"]
