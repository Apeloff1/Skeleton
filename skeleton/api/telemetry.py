"""Per-route telemetry — accumulate request timing and counts."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional


@dataclass
class RouteMetrics:
    path: str
    count: int = 0
    total_ms: float = 0.0
    errors: int = 0
    last_seen: float = 0.0

    def avg_ms(self) -> float:
        return self.total_ms / self.count if self.count else 0.0


class RouteTelemetry:
    """Record per-route request metrics; dashboards read snapshot()."""

    def __init__(self, *, clock: Optional[Callable[[], float]] = None) -> None:
        self._now = clock or time.monotonic
        self._metrics: Dict[str, RouteMetrics] = {}

    def record(self, path: str, elapsed_ms: float, *, error: bool = False) -> None:
        rec = self._metrics.setdefault(path, RouteMetrics(path=path))
        rec.count += 1
        rec.total_ms += elapsed_ms
        rec.last_seen = self._now()
        if error:
            rec.errors += 1

    def snapshot(self) -> Dict[str, dict]:
        return {
            p: {
                "count": r.count,
                "avg_ms": round(r.avg_ms(), 3),
                "errors": r.errors,
                "last_seen": r.last_seen,
            }
            for p, r in self._metrics.items()
        }
