"""Deterministic time source for replay and performance gates (#807 B071).

Provides explicit logical time for deterministic replay. It must not
replace real monotonic deadlines in production resource admission.
"""
from __future__ import annotations

import math
from typing import Callable

SCHEMA_ID = "quality.deterministic_time.v1"
DEFAULT_TICK_MS = 16.667


def _finite_nonnegative(value: object, name: str) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{name} must be a finite non-negative number")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError(f"{name} is outside the numeric range") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{name} must be a finite non-negative number")
    return number


class DeterministicClock:
    """Logical clock measured in milliseconds.

    Calling the clock returns seconds (monotonic-compatible). While frozen,
    reads never advance; when thawed, each read advances by ``tick_ms``.
    """

    __slots__ = ("_now_ms", "_tick_ms", "_frozen", "_start_ms")

    def __init__(self, tick_ms: float = DEFAULT_TICK_MS, *, start_ms: float = 0.0, frozen: bool = False) -> None:
        if type(frozen) is not bool:
            raise ValueError("frozen must be a boolean")
        self._tick_ms = _finite_nonnegative(tick_ms, "tick_ms")
        self._start_ms = _finite_nonnegative(start_ms, "start_ms")
        self._now_ms = self._start_ms
        self._frozen = frozen

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
        step = self._tick_ms if ms is None else _finite_nonnegative(ms, "advance")
        next_ms = self._now_ms + step
        if not math.isfinite(next_ms):
            raise ValueError("logical clock overflow")
        if step > 0 and next_ms == self._now_ms:
            raise ValueError("logical clock precision exhausted")
        self._now_ms = next_ms
        return self._now_ms

    def elapsed_ms(self) -> float:
        return self._now_ms - self._start_ms

    def __call__(self) -> float:
        value = self._now_ms / 1000.0
        if not self._frozen:
            self.advance()
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
    try:
        observed = _finite_nonnegative(observed_ms, "observed_ms")
        if budget_ms is None:
            return True
        budget = _finite_nonnegative(budget_ms, "budget_ms")
    except ValueError:
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
