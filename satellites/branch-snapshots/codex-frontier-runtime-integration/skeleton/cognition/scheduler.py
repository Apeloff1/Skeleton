"""Priority scheduler for bounded cognitive work."""
from __future__ import annotations

from dataclasses import dataclass, field
import heapq
from itertools import count
from typing import Any, Callable


@dataclass(order=True, slots=True)
class ScheduledWork:
    priority: float
    order: int
    name: str = field(compare=False)
    cost: int = field(compare=False, default=1)
    payload: Any = field(compare=False, default=None)


class CognitiveScheduler:
    """Deterministic priority queue with budget-aware dispatch."""

    def __init__(self, budget: int = 100) -> None:
        if budget < 0:
            raise ValueError("budget must be non-negative")
        self.budget = budget
        self.consumed = 0
        self._counter = count()
        self._queue: list[ScheduledWork] = []

    def submit(self, name: str, *, priority: float = 0.0, cost: int = 1, payload: Any = None) -> None:
        if not name:
            raise ValueError("name must be non-empty")
        if cost < 0:
            raise ValueError("cost must be non-negative")
        heapq.heappush(self._queue, ScheduledWork(-priority, next(self._counter), name, cost, payload))

    def dispatch(self, handler: Callable[[ScheduledWork], Any]) -> list[Any]:
        results: list[Any] = []
        while self._queue:
            work = heapq.heappop(self._queue)
            if self.consumed + work.cost > self.budget:
                continue
            self.consumed += work.cost
            results.append(handler(work))
        return results

    def pending(self) -> tuple[str, ...]:
        return tuple(item.name for item in sorted(self._queue))

    def reset(self, *, budget: int | None = None) -> None:
        if budget is not None:
            if budget < 0:
                raise ValueError("budget must be non-negative")
            self.budget = budget
        self.consumed = 0
