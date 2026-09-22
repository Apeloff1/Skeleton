"""Worker pool — bounded concurrent execution with backpressure.

A pool of logical workers pulling from a shared input queue with
bounded size. Producers block (or get rejected) when the queue is
full, workers report utilization and per-task latency, and the pool
integrates with the auto-scaler for dynamic resizing.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class WorkItem:
    payload: Any
    enqueued_ns: int
    attempts: int = 0


@dataclass
class WorkerStats:
    worker_id: int
    busy: bool = False
    completed: int = 0
    failed: int = 0
    total_ms: float = 0.0


class WorkerPool:
    """Bounded worker pool with queue backpressure."""

    def __init__(self, workers: int = 4, queue_capacity: int = 100):
        self._workers: List[WorkerStats] = [WorkerStats(worker_id=i) for i in range(workers)]
        self.queue_capacity = queue_capacity
        self._queue: List[WorkItem] = []
        self._rejected = 0
        self._total_completed = 0

    def resize(self, workers: int) -> None:
        current = len(self._workers)
        if workers > current:
            for i in range(current, workers):
                self._workers.append(WorkerStats(worker_id=i))
        elif workers < current:
            self._workers = self._workers[:workers]

    def submit(self, payload: Any) -> Dict[str, Any]:
        if len(self._queue) >= self.queue_capacity:
            self._rejected += 1
            return {"accepted": False, "reason": "queue full", "depth": len(self._queue)}
        self._queue.append(WorkItem(payload=payload, enqueued_ns=time.time_ns()))
        return {"accepted": True, "depth": len(self._queue)}

    def process(self, handler: Callable[[Any], Any], max_items: Optional[int] = None) -> Dict[str, Any]:
        processed = 0
        failed = 0
        while self._queue and (max_items is None or processed + failed < max_items):
            free = next((w for w in self._workers if not w.busy), None)
            if not free:
                break
            item = self._queue.pop(0)
            free.busy = True
            start = time.time_ns()
            try:
                handler(item.payload)
                free.completed += 1
                self._total_completed += 1
                processed += 1
            except Exception:  # noqa: BLE001
                free.failed += 1
                item.attempts += 1
                if item.attempts < 3:
                    self._queue.append(item)
                failed += 1
            finally:
                free.total_ms += (time.time_ns() - start) / 1e6
                free.busy = False
        return {"processed": processed, "failed": failed, "remaining": len(self._queue)}

    def utilization(self) -> float:
        busy = sum(1 for w in self._workers if w.busy)
        return busy / len(self._workers) if self._workers else 0.0

    def mean_latency_ms(self) -> float:
        total_completed = sum(w.completed + w.failed for w in self._workers)
        total_ms = sum(w.total_ms for w in self._workers)
        return total_ms / total_completed if total_completed else 0.0

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "worker-pool-card",
            "workers": len(self._workers),
            "queue_depth": len(self._queue),
            "queue_capacity": self.queue_capacity,
            "rejected": self._rejected,
            "completed": self._total_completed,
            "utilization": round(self.utilization(), 3),
            "mean_latency_ms": round(self.mean_latency_ms(), 2),
        }
