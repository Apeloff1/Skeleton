"""Auto-scaler — dynamic resource allocation based on telemetry.

Monitors subsystem load and automatically adjusts worker pool size,
cache capacity, and batch sizes. Integrates with the telemetry stream
and health probes for decision-making.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class ScalingPolicy:
    min_workers: int = 1
    max_workers: int = 10
    target_latency_ms: float = 100.0
    scale_up_threshold: float = 0.8
    scale_down_threshold: float = 0.3
    cooldown_s: float = 30.0


class AutoScaler:
    """Dynamic resource scaler with cooldown and bounds."""

    def __init__(self, subsystem: str, policy: Optional[ScalingPolicy] = None):
        self.subsystem = subsystem
        self.policy = policy or ScalingPolicy()
        self._current_workers = self.policy.min_workers
        self._last_scale_ns = 0
        self._scale_history: List[Dict[str, Any]] = []

    def evaluate(self, current_latency_ms: float, current_utilization: float) -> Dict[str, Any]:
        now = time.time_ns()
        if (now - self._last_scale_ns) / 1e9 < self.policy.cooldown_s:
            return {"action": "cooldown", "workers": self._current_workers}

        action = "hold"
        old_workers = self._current_workers

        if current_latency_ms > self.policy.target_latency_ms and current_utilization > self.policy.scale_up_threshold:
            if self._current_workers < self.policy.max_workers:
                self._current_workers = min(self.policy.max_workers, self._current_workers + 1)
                action = "scale_up"
        elif current_utilization < self.policy.scale_down_threshold:
            if self._current_workers > self.policy.min_workers:
                self._current_workers = max(self.policy.min_workers, self._current_workers - 1)
                action = "scale_down"

        if action != "hold":
            self._last_scale_ns = now
            self._scale_history.append({
                "timestamp_ns": now,
                "action": action,
                "old_workers": old_workers,
                "new_workers": self._current_workers,
                "latency_ms": current_latency_ms,
                "utilization": current_utilization,
            })

        return {"action": action, "workers": self._current_workers}

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "auto-scaler-card",
            "subsystem": self.subsystem,
            "current_workers": self._current_workers,
            "policy": {
                "min_workers": self.policy.min_workers,
                "max_workers": self.policy.max_workers,
                "target_latency_ms": self.policy.target_latency_ms,
            },
            "scale_history": self._scale_history[-5:],
        }
