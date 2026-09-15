"""Bounded micro-batching and admission control for inference workloads."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Sequence, TypeVar

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class BatchRequest(Generic[T]):
    request_id: str
    payload: T
    priority: int = 0
    cost: int = 1

    def __post_init__(self) -> None:
        if not self.request_id:
            raise ValueError("request_id is required")
        if self.cost < 1:
            raise ValueError("cost must be positive")


@dataclass(frozen=True, slots=True)
class Batch:
    requests: tuple[BatchRequest[object], ...]
    total_cost: int


class BatchScheduler(Generic[T]):
    """Stable priority scheduler with hard request and cost bounds."""

    def __init__(self, max_batch: int = 8, max_cost: int = 32) -> None:
        if max_batch < 1 or max_cost < 1:
            raise ValueError("batch bounds must be positive")
        self.max_batch = int(max_batch)
        self.max_cost = int(max_cost)
        self._queue: list[BatchRequest[T]] = []

    def submit(self, request: BatchRequest[T]) -> bool:
        if any(r.request_id == request.request_id for r in self._queue):
            return False
        self._queue.append(request)
        self._queue.sort(key=lambda r: (-r.priority, r.request_id))
        return True

    def drain(self) -> Batch[T] | None:
        if not self._queue:
            return None
        selected: list[BatchRequest[T]] = []
        cost = 0
        remaining: list[BatchRequest[T]] = []
        for request in self._queue:
            if len(selected) < self.max_batch and cost + request.cost <= self.max_cost:
                selected.append(request)
                cost += request.cost
            else:
                remaining.append(request)
        self._queue = remaining
        if not selected:
            # Never deadlock on one request larger than the budget.
            request = self._queue.pop(0)
            selected.append(request)
            cost = request.cost
        return Batch(tuple(selected), cost)

    def pending(self) -> Sequence[BatchRequest[T]]:
        return tuple(self._queue)

    def clear(self) -> None:
        self._queue.clear()


__all__ = ["Batch", "BatchRequest", "BatchScheduler"]
