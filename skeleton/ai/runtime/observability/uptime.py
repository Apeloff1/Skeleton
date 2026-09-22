"""Uptime tracking — aggregate probe outcomes into availability ratios."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Tuple

from skeleton.kernel.health import ProbeResult


@dataclass
class AvailabilityWindow:
    started_at: float
    up_count: int = 0
    down_count: int = 0

    def ratio(self) -> float:
        total = self.up_count + self.down_count
        if total == 0:
            return 1.0
        return self.up_count / total


class UptimeTracker:
    """Sliding window of probe verdicts per service."""

    def __init__(self, *, window_s: float = 86400.0, clock: Optional[Callable[[], float]] = None) -> None:
        self._window = window_s
        self._now = clock or time.monotonic
        self._records: Dict[str, AvailabilityWindow] = {}

    def record(self, service: str, ok: bool) -> None:
        rec = self._records.get(service)
        if rec is None:
            rec = self._records[service] = AvailabilityWindow(started_at=self._now())
        if ok:
            rec.up_count += 1
        else:
            rec.down_count += 1

    def availability(self, service: str) -> float:
        rec = self._records.get(service)
        return rec.ratio() if rec else 1.0

    def report(self) -> Dict[str, float]:
        return {s: rec.ratio() for s, rec in self._records.items()}
