"""background_lane — concurrency-limited lane for background work (gf BackgroundLane).

Shed first under chaos: ``try_enter`` is non-blocking and returns None when
the lane is full. Held permits are released via context-manager exit or
``release()``.

Sibling source: ``/workspace/chaos-scout/gf-background-lane.rs``
(also gf-services-lib.rs ``backpressure::BackgroundLane``).

Threading-based sync port — no asyncio. Does not touch coalesce / buffer_pool /
chaos / adaptive_gate / cortex / jeeves.
"""

from __future__ import annotations

import threading
from typing import Any, Optional


class LanePermit:
    """Held background-lane permit. Releases on ``release()`` / ``with`` exit."""

    def __init__(self, lane: "BackgroundLane") -> None:
        self._lane: Optional[BackgroundLane] = lane
        self._released = False

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        lane = self._lane
        self._lane = None
        if lane is not None:
            lane._release()

    def __enter__(self) -> "LanePermit":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.release()

    def __del__(self) -> None:
        try:
            self.release()
        except Exception:
            pass


class BackgroundLane:
    """Sync port of gf ``backpressure::BackgroundLane``. Default max_concurrent=4."""

    def __init__(self, max_concurrent: int = 4) -> None:
        if max_concurrent < 0:
            raise ValueError("max_concurrent must be non-negative")
        self._max = int(max_concurrent)
        self._open = 0
        self._lock = threading.Lock()

    def try_enter(self) -> Optional[LanePermit]:
        """Non-blocking acquire. Returns a permit token, or None when full."""
        with self._lock:
            if self._open >= self._max:
                return None
            self._open += 1
        return LanePermit(self)

    def _release(self) -> None:
        with self._lock:
            if self._open > 0:
                self._open -= 1

    def open(self) -> int:
        """Count of currently held permits."""
        with self._lock:
            return self._open

    @property
    def max_concurrent(self) -> int:
        return self._max
