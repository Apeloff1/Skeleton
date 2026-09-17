"""Explicit game clock. Process time and wall clocks are forbidden inputs."""

from __future__ import annotations

from dataclasses import dataclass


MAX_TICKS = 10_000
MIN_HZ = 1
MAX_HZ = 240


class ClockError(ValueError):
    """Clock contract violation."""


@dataclass(frozen=True, slots=True)
class GameClock:
    """Integer tick clock with an explicit rate."""

    tick: int = 0
    hz: int = 60

    def __post_init__(self) -> None:
        if not isinstance(self.tick, int) or isinstance(self.tick, bool):
            raise ClockError("tick must be an integer")
        if self.tick < 0:
            raise ClockError("tick must be >= 0")
        if not isinstance(self.hz, int) or isinstance(self.hz, bool):
            raise ClockError("hz must be an integer")
        if not MIN_HZ <= self.hz <= MAX_HZ:
            raise ClockError(f"hz must be in [{MIN_HZ}, {MAX_HZ}]")

    @property
    def seconds(self) -> float:
        return self.tick / float(self.hz)

    def advance(self, steps: int = 1) -> "GameClock":
        if not isinstance(steps, int) or isinstance(steps, bool) or steps < 1:
            raise ClockError("steps must be a positive integer")
        nxt = self.tick + steps
        if nxt > MAX_TICKS:
            raise ClockError("tick ceiling exceeded")
        return GameClock(tick=nxt, hz=self.hz)
