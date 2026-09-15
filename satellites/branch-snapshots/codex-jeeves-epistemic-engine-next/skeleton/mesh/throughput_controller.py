"""Throughput controller — AIMD concurrency control per subsystem.

Additive-increase/multiplicative-decrease concurrency limits (like
TCP Vegas): inflight limit grows slowly on success, halves on
latency spikes or errors. Finds the optimal concurrency per subsystem
without manual tuning, and coordinates with the load shedder.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class Lane:
    subsystem: str
    limit: float = 10.0
    min_limit: float = 1.0
    max_limit: float = 200.0
    inflight: int = 0
    target_latency_ms: float = 200.0
    increase_step: float = 1.0
    decrease_factor: float = 0.5
    successes: int = 0
    backoffs: int = 0


class ThroughputController:
    """AIMD concurrency limiter per subsystem lane."""

    def __init__(self):
        self._lanes: Dict[str, Lane] = {}
        self._rejected = 0

    def lane(self, subsystem: str, target_latency_ms: float = 200.0) -> Lane:
        if subsystem not in self._lanes:
            self._lanes[subsystem] = Lane(subsystem=subsystem, target_latency_ms=target_latency_ms)
        return self._lanes[subsystem]

    def acquire(self, subsystem: str) -> bool:
        lane = self.lane(subsystem)
        if lane.inflight >= int(lane.limit):
            self._rejected += 1
            return False
        lane.inflight += 1
        return True

    def release(self, subsystem: str, latency_ms: float, error: bool = False) -> None:
        lane = self.lane(subsystem)
        lane.inflight = max(0, lane.inflight - 1)
        if error or latency_ms > lane.target_latency_ms * 1.5:
            lane.limit = max(lane.min_limit, lane.limit * lane.decrease_factor)
            lane.backoffs += 1
        else:
            lane.limit = min(lane.max_limit, lane.limit + lane.increase_step / max(1, int(lane.limit)))
            lane.successes += 1

    def execute(self, subsystem: str, fn: Callable[[], Any]) -> Dict[str, Any]:
        if not self.acquire(subsystem):
            return {"executed": False, "reason": "concurrency limit"}
        start = time.time_ns()
        error = False
        result: Any = None
        try:
            result = fn()
        except Exception as exc:  # noqa: BLE001
            error = True
            result = exc
        latency_ms = (time.time_ns() - start) / 1e6
        self.release(subsystem, latency_ms, error)
        if error:
            raise result
        return {"executed": True, "result": result, "latency_ms": round(latency_ms, 2)}

    def current_limit(self, subsystem: str) -> float:
        return self.lane(subsystem).limit

    def utilization(self, subsystem: str) -> float:
        lane = self.lane(subsystem)
        return lane.inflight / lane.limit if lane.limit else 0.0

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "throughput-controller-card",
            "lanes": {n: {
                "limit": round(l.limit, 2),
                "inflight": l.inflight,
                "utilization": round(self.utilization(n), 3),
                "successes": l.successes,
                "backoffs": l.backoffs,
            } for n, l in self._lanes.items()},
            "rejected": self._rejected,
        }
