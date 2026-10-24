"""Deterministic time source for replay and performance gates (#807 B071).

Replaces wall-clock ``time.monotonic`` in quality harnesses so that replay
evidence and perf budgets are reproducible across machines and runs.
"""
from __future__ import annotations

import math
from typing import Callable

SCHEMA_ID = "quality.deterministic_time.v1"
DEFAULT_TICK_MS = 16.667


class DeterministicClock:
    """Logical clock measured in milliseconds.

    Calling the clock returns seconds (monotonic-compatible). While frozen,
    reads never advance; when thawed, each read advances by ``tick_ms``.
    """

    __slots__ = ("_now_ms", "_tick_ms", "_frozen", "_start_ms")

    def __init__(self, tick_ms: float = DEFAULT_TICK_MS, *, start_ms: float = 0.0, frozen: bool = False) -> None:
        if not math.isfinite(tick_ms) or tick_ms < 0:
            raise ValueError("tick_ms must be a finite non-negative number")
        if not math.isfinite(start_ms) or start_ms < 0:
            raise ValueError("start_ms must be a finite non-negative number")
        self._tick_ms = float(tick_ms)
        self._now_ms = float(start_ms)
        self._start_ms = float(start_ms)
        self._frozen = bool(frozen)

    @property
    def tick_ms(self) -> float:
        return self._tick_ms

    @property
    def frozen(self) -> bool:
        return self._frozen

    def now_ms(self) -> float:
        return self._now_ms

    def freeze(self) -> "DeterministicClock":
        self._frozen = True
        return self

    def thaw(self) -> "DeterministicClock":
        self._frozen = False
        return self

    def advance(self, ms: float | None = None) -> float:
        step = self._tick_ms if ms is None else float(ms)
        if not math.isfinite(step) or step < 0:
            raise ValueError("advance requires a finite non-negative step")
        self._now_ms += step
        return self._now_ms

    def elapsed_ms(self) -> float:
        return self._now_ms - self._start_ms

    def __call__(self) -> float:
        value = self._now_ms / 1000.0
        if not self._frozen:
            self._now_ms += self._tick_ms
        return value

    def to_mapping(self) -> dict[str, object]:
        return {
            "schema": SCHEMA_ID,
            "tick_ms": self._tick_ms,
            "now_ms": self._now_ms,
            "elapsed_ms": self.elapsed_ms(),
            "frozen": self._frozen,
        }


def budget_within(observed_ms: float, budget_ms: float | None) -> bool:
    """Fail closed: non-finite or negative observations never fit a budget."""
    if budget_ms is None:
        return True
    try:
        observed = float(observed_ms)
        budget = float(budget_ms)
    except (TypeError, ValueError):
        return False
    if not (math.isfinite(observed) and math.isfinite(budget)) or observed < 0 or budget < 0:
        return False
    return observed <= budget


def as_monotonic(clock: Callable[[], float] | DeterministicClock | None = None) -> Callable[[], float]:
    """Return a monotonic-compatible callable; defaults to a frozen DeterministicClock."""
    if clock is None:
        return DeterministicClock(frozen=True)
    if not callable(clock):
        raise TypeError("clock must be callable")
    return clock


__all__ = ["SCHEMA_ID", "DEFAULT_TICK_MS", "DeterministicClock", "as_monotonic", "budget_within"]
