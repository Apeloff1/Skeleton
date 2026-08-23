"""Work queue — weighted fair dequeuing for kernel task lanes.

Not all work is equal, and not all work should starve. The kernel feeds
tasks from several lanes (interactive agent turns, background dream
cycles, maintenance sweeps, telemetry flushes). A naive FIFO lets one
noisy lane starve the rest; strict priority starves the bottom lane
forever. Weighted fair queueing gives each lane a guaranteed share:

- :class:`Lane` — name, weight, and the queue itself.
- :class:`WorkQueue` — deficit-round-robin dequeuing: each pass a lane
  accrues quantum proportional to its weight, and lanes that were
  skipped keep their deficit, so long-run share converges to weight /
  total weight regardless of arrival bursts.

Bounds are explicit: per-lane capacity, global in-flight cap, and
deterministic tie-breaking so replay produces the same schedule.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Optional, Tuple

from .errors import KernelError


class WorkQueueError(KernelError):
    code = "KRN.WORK_QUEUE"


class LaneFullError(WorkQueueError):
    code = "KRN.WQ_LANE_FULL"
    http_status = 503


@dataclass(frozen=True)
class WorkItem:
    item_id: str
    payload: Any
    enqueued_seq: int = 0


@dataclass
class Lane:
    name: str
    weight: float = 1.0
    capacity: int = 1_000
    queue: Deque[WorkItem] = field(default_factory=deque)
    deficit: float = 0.0

    def __post_init__(self) -> None:
        if self.weight <= 0:
            raise WorkQueueError(
                "lane weight must be positive",
                context={"lane": self.name, "weight": self.weight},
            )
        if self.capacity < 1:
            raise WorkQueueError(
                "lane capacity must be >= 1",
                context={"lane": self.name, "capacity": self.capacity},
            )


class WorkQueue:
    """Deficit round-robin across named lanes."""

    QUANTUM = 100.0  # one dequeue unit per weight-1 lane per round

    def __init__(self, *, max_in_flight: int = 64) -> None:
        if max_in_flight < 1:
            raise WorkQueueError("max_in_flight must be >= 1")
        self.max_in_flight = max_in_flight
        self._lanes: Dict[str, Lane] = {}
        self._seq = 0
        self._in_flight = 0

    # ------------------------------------------------------------------
    # Lanes
    # ------------------------------------------------------------------

    def add_lane(self, name: str, *, weight: float = 1.0,
                 capacity: int = 1_000) -> None:
        if name in self._lanes:
            raise WorkQueueError("lane exists", context={"lane": name})
        self._lanes[name] = Lane(name=name, weight=weight, capacity=capacity)

    def lanes(self) -> Tuple[str, ...]:
        return tuple(sorted(self._lanes))

    # ------------------------------------------------------------------
    # Enqueue / dequeue
    # ------------------------------------------------------------------

    def enqueue(self, lane: str, item_id: str, payload: Any = None) -> WorkItem:
        target = self._require(lane)
        if len(target.queue) >= target.capacity:
            raise LaneFullError(
                "lane at capacity",
                context={"lane": lane, "capacity": target.capacity},
            )
        self._seq += 1
        item = WorkItem(item_id=item_id, payload=payload, enqueued_seq=self._seq)
        target.queue.append(item)
        return item

    def dequeue(self) -> Optional[Tuple[str, WorkItem]]:
        """Pick the next item fairly. Returns (lane, item) or None when
        every lane is empty or the in-flight cap is reached."""
        if self._in_flight >= self.max_in_flight:
            return None
        live = [ln for ln in self._lanes.values() if ln.queue]
        if not live:
            return None
        total_weight = sum(ln.weight for ln in live)
        for ln in live:
            ln.deficit += self.QUANTUM * (ln.weight / total_weight)
        # highest deficit first; deterministic tie-break by name
        live.sort(key=lambda ln: (-ln.deficit, ln.name))
        chosen = live[0]
        if chosen.deficit < self.QUANTUM:
            return None  # nobody has earned a turn yet
        chosen.deficit -= self.QUANTUM
        item = chosen.queue.popleft()
        self._in_flight += 1
        return chosen.name, item

    def complete(self, lane: str, item: WorkItem) -> None:
        """Mark a dequeued item done, freeing an in-flight slot."""
        if self._in_flight > 0:
            self._in_flight -= 1

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def depth(self, lane: Optional[str] = None) -> int:
        if lane is not None:
            return len(self._require(lane).queue)
        return sum(len(ln.queue) for ln in self._lanes.values())

    def report(self) -> Dict[str, Dict[str, float]]:
        return {
            name: {
                "depth": len(ln.queue),
                "weight": ln.weight,
                "deficit": round(ln.deficit, 2),
                "capacity": ln.capacity,
            }
            for name, ln in sorted(self._lanes.items())
        }

    def drain_lane(self, lane: str) -> Tuple[WorkItem, ...]:
        target = self._require(lane)
        items = tuple(target.queue)
        target.queue.clear()
        target.deficit = 0.0
        return items

    def _require(self, lane: str) -> Lane:
        target = self._lanes.get(lane)
        if target is None:
            raise WorkQueueError("unknown lane", context={"lane": lane})
        return target
