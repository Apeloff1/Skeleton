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
    ewma_latency_ms: float = 0.0
    min_latency_ms: float = 0.0


class ThroughputController:
    """AIMD + Vegas gradient concurrency limiter per subsystem lane."""

    def __init__(self):
        self._lanes: Dict[str, Lane] = {}
        self._rejected = 0

    def lane(self, subsystem: str, target_latency_ms: float = 200.0) -> Lane:
        if subsystem not in self._lanes:
            self._lanes[subsystem] = Lane(subsystem=subsystem, target_latency_ms=target_latency_ms)
        return self._lanes[subsystem]

    def acquire(self, subsystem: str, *, priority: str = "normal") -> bool:
        lane = self.lane(subsystem)
        eff_limit = max(1, int(lane.limit))
        if lane.inflight >= eff_limit:
            self._rejected += 1
            return False
        prio = str(priority or "normal").lower()
        util = float(lane.inflight) / float(eff_limit)
        if prio in {"background", "shed_first"} and eff_limit >= 2 and util >= 0.75:
            self._rejected += 1
            return False
        if prio == "normal" and eff_limit >= 4 and util >= 0.90:
            self._rejected += 1
            return False
        lane.inflight += 1
        return True

    def release(self, subsystem: str, latency_ms: float, error: bool = False) -> None:
        lane = self.lane(subsystem)
        lane.inflight = max(0, lane.inflight - 1)
        lat = max(0.0, float(latency_ms))
        if lane.ewma_latency_ms <= 0.0:
            lane.ewma_latency_ms = lat
        else:
            lane.ewma_latency_ms = 0.8 * lane.ewma_latency_ms + 0.2 * lat
        if lane.min_latency_ms <= 0.0 or (lat > 0.0 and lat < lane.min_latency_ms):
            lane.min_latency_ms = lat
        if error or lat > lane.target_latency_ms * 1.5:
            lane.limit = max(lane.min_limit, lane.limit * lane.decrease_factor)
            lane.backoffs += 1
        else:
            gradient = (lane.min_latency_ms / max(lane.ewma_latency_ms, 1e-3)) if lane.min_latency_ms > 0 else 1.0
            step = lane.increase_step * max(0.5, min(1.5, gradient))
            lane.limit = min(lane.max_limit, lane.limit + step / max(1, int(lane.limit)))
            lane.successes += 1

    def execute(self, subsystem: str, fn: Callable[[], Any], *, priority: str = "normal") -> Dict[str, Any]:
        if not self.acquire(subsystem, priority=priority):
            return {"executed": False, "reason": "concurrency limit", "priority": priority}
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
        return {"executed": True, "result": result, "latency_ms": round(latency_ms, 2), "priority": priority}

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

    def execute_coalesced_batch(
        self,
        subsystem: str,
        items: List[Any],
        batch_fn: Callable[[List[Any]], List[Any]],
        *,
        max_batch_size: int = 8,
        priority: str = "normal",
    ) -> Dict[str, Any]:
        """Coalesce multiple micro-requests into bounded vectorized batches under lane admission control."""
        if not items:
            return {"executed": True, "results": [], "batches_run": 0, "coalesced_items": 0}
        b_size = max(1, int(max_batch_size))
        results: List[Any] = []
        batches_run = 0
        total_latency_ms = 0.0
        for idx in range(0, len(items), b_size):
            chunk = items[idx:idx + b_size]
            if not self.acquire(subsystem, priority=priority):
                return {
                    "executed": False,
                    "reason": "concurrency limit",
                    "priority": priority,
                    "batches_run": batches_run,
                    "partial_results": results,
                }
            start = time.time_ns()
            error = False
            chunk_out: Any = None
            try:
                chunk_out = batch_fn(chunk)
            except Exception as exc:  # noqa: BLE001
                error = True
                chunk_out = exc
            lat_ms = (time.time_ns() - start) / 1e6
            total_latency_ms += lat_ms
            self.release(subsystem, lat_ms, error)
            if error:
                raise chunk_out
            if isinstance(chunk_out, list):
                results.extend(chunk_out)
            else:
                results.append(chunk_out)
            batches_run += 1
        return {
            "executed": True,
            "results": results,
            "batches_run": batches_run,
            "coalesced_items": len(items),
            "total_latency_ms": round(total_latency_ms, 2),
            "priority": priority,
        }
