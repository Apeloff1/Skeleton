"""Health — composable probes with liveness/readiness aggregation.

Probes are callables returning a :class:`ProbeResult`. The aggregator separates
*liveness* (is the process fundamentally alive) from *readiness* (can it serve
traffic), and computes an overall status with per-probe detail — the shape the
API's `/health/live` and `/health/ready` endpoints render directly.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ProbeResult:
    name: str
    ok: bool
    detail: str = ""
    latency_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


Probe = Callable[[], ProbeResult]


def probe(name: str):
    """Decorator: wraps a plain function into a timed Probe."""
    def wrap(fn: Callable[[], Any]) -> Probe:
        def run() -> ProbeResult:
            t0 = time.perf_counter()
            try:
                result = fn()
                ok, detail = (True, "") if result is None else (
                    bool(result.get("ok", True)), str(result.get("detail", "")))
                return ProbeResult(name, ok, detail,
                                   (time.perf_counter() - t0) * 1000.0)
            except Exception as exc:  # a crashing probe reports, never propagates
                return ProbeResult(name, False, f"{type(exc).__name__}: {exc}",
                                   (time.perf_counter() - t0) * 1000.0)
        return run
    return wrap


class HealthRegistry:
    def __init__(self) -> None:
        self._liveness: List[Probe] = []
        self._readiness: List[Probe] = []

    def add_liveness(self, p: Probe) -> None:
        self._liveness.append(p)

    def add_readiness(self, p: Probe) -> None:
        self._readiness.append(p)

    @staticmethod
    def _run(probes: List[Probe]) -> Dict[str, Any]:
        results = [p() for p in probes]
        ok = all(r.ok for r in results)
        return {"status": "up" if ok else "down",
                "probes": [{"name": r.name, "ok": r.ok, "detail": r.detail,
                            "latency_ms": round(r.latency_ms, 3)} for r in results]}

    def liveness(self) -> Dict[str, Any]:
        return self._run(self._liveness)

    def readiness(self) -> Dict[str, Any]:
        return self._run(self._readiness)
