"""SLA tracker — service-level objective monitoring with error budgets.

Tracks SLIs (availability, latency, success rate) against SLO targets
per subsystem. Computes error budgets, burn rates, and fires dashboard
alerts when budgets deplete faster than the allowed window rate.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SLOTarget:
    subsystem: str
    metric: str            # availability | latency_ms | success_rate
    target: float          # e.g. 0.999 for availability
    window_s: float = 86400.0


@dataclass
class Observation:
    timestamp_ns: int
    value: float
    good: bool


class SLATracker:
    """SLO tracking with error budget and burn rate."""

    def __init__(self):
        self._targets: Dict[str, SLOTarget] = {}
        self._observations: Dict[str, List[Observation]] = {}

    def register(self, subsystem: str, metric: str, target: float, window_s: float = 86400.0) -> SLOTarget:
        key = f"{subsystem}.{metric}"
        slo = SLOTarget(subsystem=subsystem, metric=metric, target=target, window_s=window_s)
        self._targets[key] = slo
        self._observations.setdefault(key, [])
        return slo

    def record(self, subsystem: str, metric: str, value: float, good: bool) -> None:
        key = f"{subsystem}.{metric}"
        if key not in self._targets:
            self.register(subsystem, metric, 0.99)
        self._observations[key].append(Observation(time.time_ns(), value, good))
        window_ns = self._targets[key].window_s * 1e9
        cutoff = time.time_ns() - window_ns
        self._observations[key] = [o for o in self._observations[key] if o.timestamp_ns >= cutoff]

    def compliance(self, subsystem: str, metric: str) -> Dict[str, Any]:
        key = f"{subsystem}.{metric}"
        slo = self._targets.get(key)
        obs = self._observations.get(key, [])
        if not slo or not obs:
            return {"key": key, "compliance": 1.0, "samples": 0, "error_budget_remaining": 1.0}
        good = sum(1 for o in obs if o.good)
        compliance = good / len(obs)
        budget_total = 1.0 - slo.target
        budget_consumed = max(0.0, slo.target - compliance)
        remaining = 1.0 - (budget_consumed / budget_total) if budget_total > 0 else 1.0
        return {
            "key": key,
            "compliance": round(compliance, 5),
            "target": slo.target,
            "samples": len(obs),
            "error_budget_remaining": round(max(0.0, remaining), 5),
            "breached": compliance < slo.target,
        }

    def burn_rate(self, subsystem: str, metric: str, short_window_s: float = 3600.0) -> float:
        key = f"{subsystem}.{metric}"
        slo = self._targets.get(key)
        if not slo:
            return 0.0
        obs = self._observations.get(key, [])
        if not obs:
            return 0.0
        cutoff = time.time_ns() - short_window_s * 1e9
        recent = [o for o in obs if o.timestamp_ns >= cutoff]
        if not recent:
            return 0.0
        bad_fraction = 1.0 - (sum(1 for o in recent if o.good) / len(recent))
        allowed = 1.0 - slo.target
        return bad_fraction / allowed if allowed > 0 else 0.0

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "sla-card",
            "slos": {key: self.compliance(t.subsystem, t.metric) for key, t in self._targets.items()},
            "burning_fast": [
                key for key, t in self._targets.items()
                if self.burn_rate(t.subsystem, t.metric) > 2.0
            ],
        }
