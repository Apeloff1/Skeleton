"""Bounded resilience contracts mined from gameforge-rs.

Source: Apeloff1/gameforge-rs, gf-services resilience primitives.
This module intentionally contains no framework, database, or vendor dependency.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from threading import Lock
from typing import Dict


class Lane(Enum):
    FOREGROUND = "foreground"
    BACKGROUND = "background"


@dataclass(frozen=True)
class LaneLimit:
    foreground: int
    background: int

    def __post_init__(self) -> None:
        if self.foreground < 1 or self.background < 0:
            raise ValueError("foreground must be >= 1 and background >= 0")


class BackgroundBudget:
    """Bounded background concurrency with explicit admission."""

    def __init__(self, limit: int = 4) -> None:
        if limit < 0:
            raise ValueError("limit must be non-negative")
        self._limit = limit
        self._active = 0
        self._lock = Lock()

    def try_acquire(self) -> bool:
        with self._lock:
            if self._active >= self._limit:
                return False
            self._active += 1
            return True

    def release(self) -> None:
        with self._lock:
            if self._active == 0:
                return
            self._active -= 1

    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {"active": self._active, "limit": self._limit}


class Degradation(Enum):
    NORMAL = 0
    REDUCED_CACHING = 1
    SHED_BACKGROUND = 2
    STALE_READS = 3
    EMERGENCY_READ_ONLY = 4


class DegradationPolicy:
    """Monotonic fail-safe degradation state machine."""

    def __init__(self) -> None:
        self._state = Degradation.NORMAL
        self._lock = Lock()

    @property
    def state(self) -> Degradation:
        with self._lock:
            return self._state

    @property
    def read_only(self) -> bool:
        return self.state is Degradation.EMERGENCY_READ_ONLY

    @property
    def background_allowed(self) -> bool:
        return self.state.value < Degradation.SHED_BACKGROUND.value

    def degrade(self) -> Degradation:
        with self._lock:
            if self._state.value < Degradation.EMERGENCY_READ_ONLY.value:
                self._state = Degradation(self._state.value + 1)
            return self._state

    def recover(self) -> Degradation:
        with self._lock:
            if self._state.value > Degradation.NORMAL.value:
                self._state = Degradation(self._state.value - 1)
            return self._state
