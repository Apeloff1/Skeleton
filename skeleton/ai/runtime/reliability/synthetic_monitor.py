"""Synthetic monitor — proactive end-to-end transaction probes.

Runs scripted user journeys (login → dashboard → action) against the
live system on a schedule, measuring step-level latency and success.
Detects failures before users do, tracks probe uptime, and fires
dashboard alerts on consecutive failures. Complements health probes
with full-stack realism.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class StepResult:
    name: str
    ok: bool
    duration_ms: float
    error: Optional[str] = None


@dataclass
class ProbeRun:
    journey: str
    started_ns: int
    steps: List[StepResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(s.ok for s in self.steps)

    @property
    def total_ms(self) -> float:
        return sum(s.duration_ms for s in self.steps)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "journey": self.journey,
            "ok": self.ok,
            "total_ms": round(self.total_ms, 2),
            "steps": [{"name": s.name, "ok": s.ok, "ms": round(s.duration_ms, 2), "error": s.error} for s in self.steps],
        }


@dataclass
class Journey:
    name: str
    steps: List[tuple]
    consecutive_failures: int = 0
    runs: int = 0
    failures: int = 0


class SyntheticMonitor:
    """Scheduled end-to-end journey probing."""

    def __init__(self, alert_after_failures: int = 3):
        self._journeys: Dict[str, Journey] = {}
        self._history: List[ProbeRun] = []
        self.alert_after_failures = alert_after_failures

    def register(self, name: str, steps: List[tuple]) -> Journey:
        j = Journey(name=name, steps=steps)
        self._journeys[name] = j
        return j

    def run(self, name: str) -> ProbeRun:
        journey = self._journeys[name]
        probe = ProbeRun(journey=name, started_ns=time.time_ns())
        for step_name, fn in journey.steps:
            start = time.time_ns()
            try:
                fn()
                result = StepResult(step_name, True, (time.time_ns() - start) / 1e6)
            except Exception as exc:  # noqa: BLE001
                result = StepResult(step_name, False, (time.time_ns() - start) / 1e6, str(exc))
            probe.steps.append(result)
            if not result.ok:
                break
        journey.runs += 1
        if probe.ok:
            journey.consecutive_failures = 0
        else:
            journey.failures += 1
            journey.consecutive_failures += 1
        self._history.append(probe)
        if len(self._history) > 200:
            self._history.pop(0)
        return probe

    def run_all(self) -> List[Dict[str, Any]]:
        return [self.run(name).to_dict() for name in self._journeys]

    def alerting_journeys(self) -> List[str]:
        return [n for n, j in self._journeys.items() if j.consecutive_failures >= self.alert_after_failures]

    def uptime(self, name: str) -> float:
        j = self._journeys.get(name)
        if not j or j.runs == 0:
            return 1.0
        return 1.0 - (j.failures / j.runs)

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "synthetic-monitor-card",
            "journeys": {n: {
                "runs": j.runs,
                "uptime": round(self.uptime(n), 4),
                "consecutive_failures": j.consecutive_failures,
                "alerting": j.consecutive_failures >= self.alert_after_failures,
            } for n, j in self._journeys.items()},
            "alerting": self.alerting_journeys(),
            "recent": [p.to_dict() for p in self._history[-5:]],
        }
