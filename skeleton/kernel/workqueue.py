"""In-process work-queue with priorities, fairness, and backpressure hooks.

Agents submit work faster than they can drain it; without a queue the
kernel either blocks producers (coupling) or drops work (loss). This
queue sits between intake and execution:

- :class:`WorkItem` — priority, cost estimate, submitter, deadline.
- :class:`FairWorkQueue` — strict-priority levels with weighted-fair
  interleaving inside each level so a chatty submitter can't starve
  peers; ``dequeue`` returns items whose deadlines are still reachable
  and reports the expired ones instead of running zombie work.
- Capacity is bounded and admission composes with the kernel
  backpressure governor via the ``on_pressure`` hook.

Single-threaded ownership model (the dispatcher drains it); no locks.
"""

from __future__ import annotations

import heapq
import itertools
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from .errors import KernelError


class QueueError(KernelError):
    code = "KRN.QUEUE"


class QueueFullError(QueueError):
    code = "KRN.QUEUE_FULL"
    http_status = 503


@dataclass(order=True)
class _Entry:
    sort_key: Tuple[int, float, int]
    item: "WorkItem" = field(compare=False)


@dataclass(frozen=True)
class WorkItem:
    work_id: str
    submitter: str
    priority: int = 0            # higher runs sooner
    cost: float = 1.0            # abstract execution cost units
    deadline: Optional[float] = None
    enqueued_at: float = 0.0


@dataclass(frozen=True)
class DequeueResult:
    item: Optional[WorkItem]
    expired: Tuple[str, ...]     # work ids dropped this call


class FairWorkQueue:
    """Bounded, priority-aware queue with per-submitter fairness."""

    def __init__(
        self,
        *,
        capacity: int = 10_000,
        per_submitter_cap: int = 1_000,
        clock: Optional[Callable[[], float]] = None,
        on_pressure: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        if capacity < 1 or per_submitter_cap < 1 or per_submitter_cap > capacity:
            raise QueueError(
                "capacity bounds invalid",
                context={"capacity": capacity, "per_submitter": per_submitter_cap},
            )
        self.capacity = capacity
        self.per_submitter_cap = per_submitter_cap
        self._now = clock or time.monotonic
        self._on_pressure = on_pressure
        self._heap: List[_Entry] = []
        self._counter = itertools.count()
        self._submitter_counts: Dict[str, int] = {}
        self._rr_cursor: Dict[str, float] = {}  # submitter -> virtual finish

    def __len__(self) -> int:
        return len(self._heap)

    # ------------------------------------------------------------------
    # Intake
    # ------------------------------------------------------------------

    def enqueue(self, item: WorkItem) -> None:
        if len(self._heap) >= self.capacity:
            raise QueueFullError(
                "work queue at capacity",
                context={"capacity": self.capacity, "work": item.work_id},
            )
        count = self._submitter_counts.get(item.submitter, 0)
        if count >= self.per_submitter_cap:
            raise QueueFullError(
                "submitter at fair-share cap",
                context={"submitter": item.submitter,
                         "cap": self.per_submitter_cap},
            )
        stamped = item if item.enqueued_at else WorkItem(
            **{**item.__dict__, "enqueued_at": self._now()})
        # fairness key: submitter's virtual finish time, then priority, FIFO
        vf = self._rr_cursor.get(item.submitter, 0.0)
        key = (-stamped.priority, vf, next(self._counter))
        heapq.heappush(self._heap, _Entry(key, stamped))
        self._submitter_counts[item.submitter] = count + 1
        if self._on_pressure is not None:
            self._on_pressure(len(self._heap), self.capacity)

    # ------------------------------------------------------------------
    # Drain
    # ------------------------------------------------------------------

    def dequeue(self) -> DequeueResult:
        expired: List[str] = []
        now = self._now()
        while self._heap:
            entry = heapq.heappop(self._heap)
            item = entry.item
            self._submitter_counts[item.submitter] -= 1
            if item.deadline is not None and now > item.deadline:
                expired.append(item.work_id)
                continue
            # charge the submitter's virtual time by actual cost
            self._rr_cursor[item.submitter] = (
                self._rr_cursor.get(item.submitter, 0.0) + item.cost)
            return DequeueResult(item, tuple(expired))
        return DequeueResult(None, tuple(expired))

    def peek(self, n: int = 5) -> Tuple[WorkItem, ...]:
        return tuple(e.item for e in sorted(self._heap)[:n])

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def stats(self) -> Dict[str, object]:
        return {
            "depth": len(self._heap),
            "capacity": self.capacity,
            "submitters": dict(self._submitter_counts),
            "utilisation": round(len(self._heap) / self.capacity, 4),
        }

    def drop_submitter(self, submitter: str) -> int:
        """Evict everything from one submitter (e.g. a dead agent)."""
        keep = [e for e in self._heap if e.item.submitter != submitter]
        dropped = len(self._heap) - len(keep)
        heapq.heapify(keep)
        self._heap = keep
        self._submitter_counts.pop(submitter, None)
        self._rr_cursor.pop(submitter, None)
        return dropped
