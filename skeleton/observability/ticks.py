"""Observability tick aggregation — turn probes into periodic summaries.

HealthRegistry.readiness() snapshots every probe; TickAggregator
accumulates probe reports per rolling window (e.g. per minute) and
produces a summary with status counts and slowest probe — the kind
the dashboard widget renders as a sparkline.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from skeleton.kernel.health import ProbeReport, ProbeResult, ProbeStatus


@dataclass
class TickStats:
    probes: int = 0
    ok: int = 0
    degraded: int = 0
    failed: int = 0
    slowest_probe: Optional[str] = None
    slowest_duration_s: float = 0.0
    window_started: float = 0.0

    def add(self, report: ProbeReport) -> None:
        self.probes += 1
        duration = report.duration_s
        if duration > self.slowest_duration_s:
            self.slowest_probe = report.name
            self.slowest_duration_s = duration
        if report.result.status is ProbeStatus.OK:
            self.ok += 1
        elif report.result.status is ProbeStatus.DEGRADED:
            self.degraded += 1
        else:
            self.failed += 1


class TickAggregator:
    """Aggregate a batch of probe reports per window."""

    def __init__(self, *, window_s: float = 60.0, clock: Optional[Callable[[], float]] = None) -> None:
        self.window_s = window_s
        self._now = clock or time.monotonic
        self._current = TickStats(window_started=self._now())
        self._history: List[TickStats] = []

    def record(self, reports: Tuple[ProbeReport, ...]) -> None:
        if self._now() - self._current.window_started >= self.window_s:
            self._history.append(self._current)
            self._current = TickStats(window_started=self._now())
        for report in reports:
            self._current.add(report)

    def current(self) -> TickStats:
        return self._current

    def history(self, n: int = 10) -> Tuple[TickStats, ...]:
        return tuple(self._history[-n:])
