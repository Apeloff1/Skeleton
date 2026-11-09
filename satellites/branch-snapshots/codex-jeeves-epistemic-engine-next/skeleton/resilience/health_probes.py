"""Health probe aggregator — composite health checks with dependency graphs.

Runs periodic health probes across all subsystems, computes composite
health scores, and exposes a readiness/liveness model for orchestrators.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ProbeResult:
    name: str
    healthy: bool
    latency_ms: float
    message: str
    timestamp_ns: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "healthy": self.healthy,
            "latency_ms": self.latency_ms,
            "message": self.message,
            "timestamp_ns": self.timestamp_ns,
        }


class HealthProbeAggregator:
    """Composite health probe with dependency graph."""

    def __init__(self):
        self._probes: Dict[str, Callable[[], ProbeResult]] = {}
        self._dependencies: Dict[str, List[str]] = {}
        self._results: Dict[str, ProbeResult] = {}
        self._last_run_ns = 0

    def register(self, name: str, fn: Callable[[], ProbeResult], depends_on: Optional[List[str]] = None) -> None:
        self._probes[name] = fn
        if depends_on:
            self._dependencies[name] = depends_on

    def run_all(self) -> Dict[str, Any]:
        self._results.clear()
        for name in self._topological_order():
            start = time.time_ns()
            try:
                result = self._probes[name]()
            except Exception as exc:
                result = ProbeResult(name=name, healthy=False, latency_ms=0.0, message=str(exc), timestamp_ns=time.time_ns())
            result.latency_ms = (time.time_ns() - start) / 1e6
            deps = self._dependencies.get(name, [])
            if any(not self._results[d].healthy for d in deps if d in self._results):
                result.healthy = False
                result.message = f"dependency unhealthy: {deps}"
            self._results[name] = result
        self._last_run_ns = time.time_ns()
        return self.card()

    def _topological_order(self) -> List[str]:
        visited: set = set()
        order: List[str] = []

        def visit(n: str) -> None:
            if n in visited:
                return
            visited.add(n)
            for d in self._dependencies.get(n, []):
                visit(d)
            order.append(n)

        for name in self._probes:
            visit(name)
        return order

    def readiness(self) -> bool:
        return all(r.healthy for r in self._results.values())

    def liveness(self) -> bool:
        return self._last_run_ns > 0 and (time.time_ns() - self._last_run_ns) < 30e9

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "health-probe-card",
            "readiness": self.readiness(),
            "liveness": self.liveness(),
            "probes": {name: r.to_dict() for name, r in self._results.items()},
            "unhealthy": [name for name, r in self._results.items() if not r.healthy],
        }
