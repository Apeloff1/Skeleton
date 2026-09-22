"""Retention sweeps — drop aged spans/metrics snapshots on sched.

InMemoryExporter holds up to `capacity` spans; dashboards or exporters
may want an age-based sweep, not just FIFO rollback. The sweeper
clears a stored sequence of span objects older than TTL.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Tuple


@dataclass
class SweepStats:
    swept: int = 0
    retained: int = 0

    def add(self, swept: bool) -> None:
        if swept:
            self.swept += 1
        else:
            self.retained += 1


class RetentionSweeper:
    """TTL-based deletion helper over timestamped sequences."""

    def __init__(self, *, ttl_s: float, clock: Optional[Callable[[], float]] = None) -> None:
        self.ttl_s = ttl_s
        self._now = clock or time.time
        self._stats = SweepStats()

    def sweep(self, entries: List[Any], *, timestamp_of: Callable[[Any], float]) -> List[Any]:
        if self.ttl_s <= 0:
            return entries
        cutoff = self._now() - self.ttl_s
        kept: List[Any] = []
        for entry in entries:
            if timestamp_of(entry) < cutoff:
                self._stats.add(swept=True)
                continue
            kept.append(entry)
            self._stats.add(swept=False)
        return kept

    def stats(self) -> SweepStats:
        return self._stats
