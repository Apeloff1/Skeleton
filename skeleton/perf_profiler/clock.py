"""Injectable clocks. All profiler timing goes through ``Clock.now_ms``."""
from __future__ import annotations

import math
import time
from typing import Iterable, Protocol


class Clock(Protocol):
    def now_ms(self) -> float: ...


class MonotonicClock:
    """Real clock backed by ``time.perf_counter_ns``."""

    def now_ms(self) -> float:
        return time.perf_counter_ns() / 1_000_000.0


class DeterministicClock:
    """Manually driven clock for reproducible tests and replays.

    ``now_ms`` never advances on its own. Use ``advance`` or preload a
    ``script`` of deltas that are consumed one per ``now_ms`` call after the
    first (so ``start``/``stop`` pairs observe the scripted durations).
    """

    def __init__(self, start_ms: float = 0.0, script: Iterable[float] = ()) -> None:
        _check_finite(start_ms, "start_ms")
        self._now = float(start_ms)
        raw = list(script)
        for d in raw:
            _check_delta(d)
        self._script = [float(d) for d in raw]
        self._primed = False

    def advance(self, delta_ms: float) -> float:
        _check_delta(delta_ms)
        self._now += float(delta_ms)
        return self._now

    def now_ms(self) -> float:
        if self._primed and self._script:
            self._now += self._script.pop(0)
        self._primed = True
        return self._now

    @property
    def remaining_script(self) -> int:
        return len(self._script)


def _check_finite(value: float, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number, got {value!r}")


def _check_delta(delta: float) -> None:
    _check_finite(delta, "delta_ms")
    if delta < 0:
        raise ValueError(f"clock cannot go backwards (delta_ms={delta!r})")
