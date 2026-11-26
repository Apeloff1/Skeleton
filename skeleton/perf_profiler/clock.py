"""Injectable clocks. All profiler timing goes through ``Clock.now_ms``."""
from __future__ import annotations

MAX_SCRIPT_STEPS = 1000

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
    """Scripted clock. Each ``now_ms`` returns the next value from the script.

    The script is a finite iterable of millisecond values. Once exhausted,
    further calls raise ``StopIteration``.
    """

    def __init__(self, script: Iterable[float]) -> None:
        self._iter = iter(script)

    def now_ms(self) -> float:
        return next(self._iter)
