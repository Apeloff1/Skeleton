"""Adaptive load shedder — dynamic backpressure and request shedding.

Monitors subsystem health and sheds load when latency, error rate,
or queue depth exceeds thresholds. Integrates with telemetry stream
and circuit breaker for coordinated resilience.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class SheddingPolicy:
    max_latency_ms: float = 500.0
    max_error_rate: float = 0.25
    max_queue_depth: int = 100
    shedding_rate: float = 0.0

    def should_shed(self, latency_ms: float, error_rate: float, queue_depth: int) -> bool:
        return (
            latency_ms > self.max_latency_ms
            or error_rate > self.max_error_rate
            or queue_depth > self.max_queue_depth
        )


class LoadShedder:
    """Adaptive load shedder with gradient-based rate adjustment."""

    def __init__(self, subsystem: str, policy: Optional[SheddingPolicy] = None):
        self.subsystem = subsystem
        self.policy = policy or SheddingPolicy()
        self._latency_window: List[float] = []
        self._error_window: List[bool] = []
        self._queue_depth = 0
        self._shed_count = 0
        self._total_count = 0
        self._last_adjust_ns = time.time_ns()

    def record_request(self, latency_ms: float, error: bool = False) -> None:
        self._latency_window.append(latency_ms)
        if len(self._latency_window) > 100:
            self._latency_window.pop(0)
        self._error_window.append(error)
        if len(self._error_window) > 100:
            self._error_window.pop(0)
        self._total_count += 1

    def set_queue_depth(self, depth: int) -> None:
        self._queue_depth = depth

    def admit(self) -> bool:
        latency = sum(self._latency_window) / max(1, len(self._latency_window))
        error_rate = sum(1 for e in self._error_window if e) / max(1, len(self._error_window))
        if self.policy.should_shed(latency, error_rate, self._queue_depth):
            self._shed_count += 1
            self._adjust_up()
            return False
        self._adjust_down()
        return True

    def _adjust_up(self) -> None:
        now = time.time_ns()
        if now - self._last_adjust_ns > 1e9:
            self.policy.shedding_rate = min(1.0, self.policy.shedding_rate + 0.1)
            self._last_adjust_ns = now

    def _adjust_down(self) -> None:
        now = time.time_ns()
        if now - self._last_adjust_ns > 1e9:
            self.policy.shedding_rate = max(0.0, self.policy.shedding_rate - 0.05)
            self._last_adjust_ns = now

    def card(self) -> Dict[str, Any]:
        latency = sum(self._latency_window) / max(1, len(self._latency_window))
        error_rate = sum(1 for e in self._error_window if e) / max(1, len(self._error_window))
        return {
            "kind": "load-shedder-card",
            "subsystem": self.subsystem,
            "mean_latency_ms": round(latency, 2),
            "error_rate": round(error_rate, 3),
            "queue_depth": self._queue_depth,
            "shedding_rate": round(self.policy.shedding_rate, 2),
            "shed_count": self._shed_count,
            "total_count": self._total_count,
        }
