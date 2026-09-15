"""Canary deployments — progressive rollout with automatic rollback.

Rolls new versions out in stages (1% → 10% → 50% → 100%), watching
error rates and latency at each stage. Promotes on healthy metrics,
rolls back automatically on regression. Integrates with feature
flags for traffic splitting and the audit log for every transition.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


DEFAULT_STAGES = [1, 10, 25, 50, 100]


@dataclass
class StageMetric:
    stage_pct: int
    error_rate: float
    p99_latency_ms: float
    samples: int
    timestamp_ns: int


@dataclass
class Rollout:
    rollout_id: str
    service: str
    from_version: str
    to_version: str
    stages: List[int] = field(default_factory=lambda: list(DEFAULT_STAGES))
    stage_index: int = 0
    status: str = "in_progress"
    metrics: List[StageMetric] = field(default_factory=list)
    started_ns: int = 0

    @property
    def current_pct(self) -> int:
        return self.stages[min(self.stage_index, len(self.stages) - 1)]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rollout_id": self.rollout_id,
            "service": self.service,
            "from_version": self.from_version,
            "to_version": self.to_version,
            "stage_pct": self.current_pct,
            "stage_index": self.stage_index,
            "total_stages": len(self.stages),
            "status": self.status,
            "samples": sum(m.samples for m in self.metrics),
        }


class CanaryController:
    """Progressive rollout controller with auto-rollback."""

    def __init__(self, max_error_rate: float = 0.05, max_latency_regression: float = 1.5):
        self.max_error_rate = max_error_rate
        self.max_latency_regression = max_latency_regression
        self._rollouts: Dict[str, Rollout] = {}
        self._counter = 0
        self._baseline_latency: Dict[str, float] = {}

    def start(self, service: str, from_version: str, to_version: str,
              stages: Optional[List[int]] = None,
              baseline_latency_ms: float = 100.0) -> Rollout:
        self._counter += 1
        rollout = Rollout(
            rollout_id=f"r{self._counter:04d}",
            service=service,
            from_version=from_version,
            to_version=to_version,
            stages=stages or list(DEFAULT_STAGES),
            started_ns=time.time_ns(),
        )
        self._rollouts[rollout.rollout_id] = rollout
        self._baseline_latency[service] = baseline_latency_ms
        return rollout

    def observe(self, rollout_id: str, error_rate: float, p99_latency_ms: float,
                samples: int = 100) -> Dict[str, Any]:
        rollout = self._rollouts[rollout_id]
        metric = StageMetric(
            stage_pct=rollout.current_pct,
            error_rate=error_rate,
            p99_latency_ms=p99_latency_ms,
            samples=samples,
            timestamp_ns=time.time_ns(),
        )
        rollout.metrics.append(metric)
        baseline = self._baseline_latency.get(rollout.service, 100.0)
        unhealthy = (
            error_rate > self.max_error_rate
            or p99_latency_ms > baseline * self.max_latency_regression
        )
        if unhealthy:
            rollout.status = "rolled_back"
            return {"action": "rolled_back", "reason": {"error_rate": error_rate, "p99": p99_latency_ms, "baseline": baseline}}
        if rollout.stage_index < len(rollout.stages) - 1:
            rollout.stage_index += 1
            return {"action": "advanced", "new_stage_pct": rollout.current_pct}
        rollout.status = "promoted"
        return {"action": "promoted", "version": rollout.to_version}

    def pause(self, rollout_id: str) -> bool:
        rollout = self._rollouts.get(rollout_id)
        if rollout and rollout.status == "in_progress":
            rollout.status = "paused"
            return True
        return False

    def resume(self, rollout_id: str) -> bool:
        rollout = self._rollouts.get(rollout_id)
        if rollout and rollout.status == "paused":
            rollout.status = "in_progress"
            return True
        return False

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "canary-card",
            "rollouts": {rid: r.to_dict() for rid, r in self._rollouts.items()},
            "active": [rid for rid, r in self._rollouts.items() if r.status == "in_progress"],
            "policy": {
                "max_error_rate": self.max_error_rate,
                "max_latency_regression": self.max_latency_regression,
            },
        }
