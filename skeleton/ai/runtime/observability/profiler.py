"""Profiler — lightweight function and subsystem performance profiling.

Profiles call durations with statistical breakdowns (p50/p95/p99),
identifies hot paths, tracks regression vs historical baselines, and
exports flame-graph-compatible folded stacks for offline analysis.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ProfileSample:
    name: str
    duration_ms: float
    timestamp_ns: int
    tags: Dict[str, str] = field(default_factory=dict)


class Profiler:
    """Explicit-span profiler with percentile stats and baselines."""

    def __init__(self, max_samples_per_name: int = 1000):
        self._samples: Dict[str, List[ProfileSample]] = {}
        self._baselines: Dict[str, float] = {}
        self.max_samples = max_samples_per_name

    def record(self, name: str, duration_ms: float, **tags: str) -> ProfileSample:
        sample = ProfileSample(name=name, duration_ms=duration_ms, timestamp_ns=time.time_ns(), tags=tags)
        buf = self._samples.setdefault(name, [])
        buf.append(sample)
        if len(buf) > self.max_samples:
            buf.pop(0)
        return sample

    def profile(self, name: str, fn: Callable[[], Any], **tags: str) -> Any:
        start = time.time_ns()
        try:
            return fn()
        finally:
            self.record(name, (time.time_ns() - start) / 1e6, **tags)

    def stats(self, name: str) -> Dict[str, Any]:
        buf = self._samples.get(name, [])
        if not buf:
            return {"name": name, "samples": 0}
        durations = sorted(s.duration_ms for s in buf)
        n = len(durations)
        return {
            "name": name,
            "samples": n,
            "mean_ms": round(sum(durations) / n, 3),
            "p50_ms": round(durations[n // 2], 3),
            "p95_ms": round(durations[min(n - 1, int(n * 0.95))], 3),
            "p99_ms": round(durations[min(n - 1, int(n * 0.99))], 3),
            "max_ms": round(durations[-1], 3),
            "baseline_ms": self._baselines.get(name),
            "regression_pct": self._regression(name, durations),
        }

    def _regression(self, name: str, durations: List[float]) -> Optional[float]:
        baseline = self._baselines.get(name)
        if not baseline:
            return None
        mean = sum(durations) / len(durations)
        return round((mean - baseline) / baseline * 100, 1)

    def set_baseline(self, name: str) -> None:
        buf = self._samples.get(name, [])
        if buf:
            self._baselines[name] = sum(s.duration_ms for s in buf) / len(buf)

    def hot_paths(self, limit: int = 10) -> List[Dict[str, Any]]:
        scored = []
        for name, buf in self._samples.items():
            if buf:
                total = sum(s.duration_ms for s in buf)
                scored.append((total, name, len(buf)))
        scored.sort(reverse=True)
        return [{"name": n, "total_ms": round(t, 2), "calls": c} for t, n, c in scored[:limit]]

    def folded_stacks(self, name: str) -> str:
        buf = self._samples.get(name, [])
        return "\n".join(f"{s.name} {s.duration_ms:.3f}" for s in buf)

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "profiler-card",
            "profiled": len(self._samples),
            "total_samples": sum(len(b) for b in self._samples.values()),
            "hot_paths": self.hot_paths(5),
            "baselines": len(self._baselines),
        }
