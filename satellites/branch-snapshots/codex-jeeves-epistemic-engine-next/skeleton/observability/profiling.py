"""Span-derived profiler — aggregates tracing spans into per-name stats.

Traces are events; profiling is aggregation. The profiler subscribes to a
SpanRecorder-style sink and computes per-span-name counts, durations,
p50/p99, and error rates — the shape a perf dashboard renders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from skeleton.kernel.trace import Span, SpanStatus, TraceError


@dataclass
class SpanStats:
    name: str
    count: int = 0
    error_count: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0
    _durations: List[float] = field(default_factory=list)

    def record(self, span: Span) -> None:
        duration = (span.finished_at or 0.0) - span.started_at
        ms = duration * 1000.0
        self.count += 1
        self.total_ms += ms
        self.max_ms = max(self.max_ms, ms)
        self._durations.append(ms)
        if span.status is SpanStatus.ERROR:
            self.error_count += 1

    def summary(self) -> Dict[str, float]:
        ordered = sorted(self._durations)

        def quantile(q: float) -> float:
            if not ordered:
                return 0.0
            idx = min(int(q * len(ordered)), len(ordered) - 1)
            return ordered[idx]

        return {
            "count": float(self.count),
            "error_rate": self.error_count / max(self.count, 1),
            "avg_ms": self.total_ms / max(self.count, 1),
            "p50_ms": quantile(0.5),
            "p99_ms": quantile(0.99),
            "max_ms": self.max_ms,
        }


class Profiler:
    """In-memory aggregation of spans by operation name."""

    def __init__(self) -> None:
        self._stats: Dict[str, SpanStats] = {}

    def record(self, span: Span) -> None:
        stats = self._stats.setdefault(span.name, SpanStats(name=span.name))
        stats.record(span)

    def report(self, name: Optional[str] = None) -> Dict[str, Dict[str, float]]:
        if name is not None:
            stats = self._stats.get(name)
            if stats is None:
                raise TraceError("unknown span name", context={"name": name})
            return {name: stats.summary()}
        return {n: s.summary() for n, s in self._stats.items()}

    def slowest(self, n: int = 5) -> Tuple[Tuple[str, Dict[str, float]], ...]:
        ranked = sorted(
            ((n, s.summary()) for n, s in self._stats.items()),
            key=lambda kv: -kv[1]["avg_ms"],
        )
        return tuple(ranked[:n])
