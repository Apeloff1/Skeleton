"""Explicit wall/monotonic time primitives for VOL-297.

Elapsed-duration correctness is based only on monotonic ticks. UTC wall time is
kept as boundary metadata and is never used to decide deadline expiration.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
import math
import time


@dataclass(frozen=True, order=True)
class Duration:
    seconds: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.seconds) or self.seconds < 0:
            raise ValueError("duration must be finite and non-negative")


@dataclass(frozen=True)
class Instant:
    monotonic_seconds: float
    utc: datetime

    def __post_init__(self) -> None:
        if not math.isfinite(self.monotonic_seconds):
            raise ValueError("monotonic instant must be finite")
        if self.utc.tzinfo is None or self.utc.utcoffset() is None:
            raise ValueError("wall-clock instant must be timezone-aware")
        if self.utc.utcoffset() != timezone.utc.utcoffset(self.utc):
            raise ValueError("instant boundary must be normalized to UTC")

    def elapsed_since(self, earlier: "Instant") -> Duration:
        delta = self.monotonic_seconds - earlier.monotonic_seconds
        if delta < 0:
            raise ValueError("monotonic clock moved backwards")
        return Duration(delta)


@dataclass(frozen=True)
class Deadline:
    monotonic_seconds: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.monotonic_seconds):
            raise ValueError("deadline must be finite")

    @classmethod
    def after(cls, instant: Instant, duration: Duration) -> "Deadline":
        target = instant.monotonic_seconds + duration.seconds
        if not math.isfinite(target):
            raise ValueError("deadline overflow")
        return cls(target)

    def remaining(self, now: Instant) -> Duration:
        return Duration(max(0.0, self.monotonic_seconds - now.monotonic_seconds))

    def expired(self, now: Instant) -> bool:
        return now.monotonic_seconds >= self.monotonic_seconds


class Clock(Protocol):
    def now(self) -> Instant: ...


class SystemClock:
    def now(self) -> Instant:
        return Instant(time.monotonic(), datetime.now(timezone.utc))


class ManualClock:
    """Deterministic injectable clock for tests, replay and simulation."""

    def __init__(self, instant: Instant) -> None:
        self._instant = instant

    def now(self) -> Instant:
        return self._instant

    def advance(self, duration: Duration) -> Instant:
        self._instant = Instant(
            self._instant.monotonic_seconds + duration.seconds,
            self._instant.utc + duration_to_timedelta(duration),
        )
        return self._instant

    def set_wall_time(self, utc: datetime) -> Instant:
        self._instant = Instant(self._instant.monotonic_seconds, utc)
        return self._instant


def duration_to_timedelta(duration: Duration):
    from datetime import timedelta
    return timedelta(seconds=duration.seconds)
