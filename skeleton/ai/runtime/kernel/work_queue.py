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

Optional policies ported from the retired ``fair_queue`` plane:

- **Deadlines** — items may carry an absolute ``deadline``; ``dequeue``
  retires expired work (counted under ``stats.expired``) instead of
  running zombie tasks.
- **Per-submitter caps** — when constructed with ``per_submitter_cap``,
  enqueue rejects work from a submitter already holding that many queued
  items, so one chatty producer can't flood every lane.

Scheduler invariants:

- ``dequeue`` never reports an empty result merely because fairness credit
  has not reached one quantum yet. If runnable work exists and an
  in-flight slot is available, credit is advanced internally until a lane
  earns a turn.
- In-flight capacity is derived from tracked work rather than a loose
  counter. ``complete`` must match the exact dequeued lane/item pair, so
  duplicate or cross-lane completion cannot free another task's slot.
- Submitter accounting removes zero-count entries, keeping the fairness
  ledger bounded by active queued submitters.

The deadline and submitter policies remain opt-in.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, Optional, Tuple

from .errors import KernelError


class WorkQueueError(KernelError):
    code = "KRN.WORK_QUEUE"


class LaneFullError(WorkQueueError):
    code = "KRN.WQ_LANE_FULL"
    http_status = 503


class SubmitterCapError(WorkQueueError):
    code = "KRN.WQ_SUBMITTER_CAP"
    http_status = 503


class CompletionError(WorkQueueError):
    """Raised when completion does not match an active dequeue lease."""

    code = "KRN.WQ_COMPLETION"
    http_status = 409


@dataclass(frozen=True)
class WorkItem:
    item_id: str
    payload: Any
    enqueued_seq: int = 0
    submitter: Optional[str] = None
    deadline: Optional[float] = None  # absolute epoch seconds; None = never

    def is_expired(self, now: Optional[float] = None) -> bool:
        if self.deadline is None:
            return False
        return (now if now is not None else time.time()) >= self.deadline


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

    def __init__(
        self,
        *,
        max_in_flight: int = 64,
        per_submitter_cap: Optional[int] = None,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        if max_in_flight < 1:
            raise WorkQueueError("max_in_flight must be >= 1")
        if per_submitter_cap is not None and per_submitter_cap < 1:
            raise WorkQueueError("per_submitter_cap must be >= 1 when set")
        self.max_in_flight = max_in_flight
        self.per_submitter_cap = per_submitter_cap
        self._now = clock or time.time
        self._lanes: Dict[str, Lane] = {}
        self._seq = 0
        self._in_flight_items: Dict[int, Tuple[str, WorkItem]] = {}
        self._submitter_counts: Dict[str, int] = {}
        self._expired = 0
        self._completion_errors = 0

    # ------------------------------------------------------------------
    # Lanes
    # ------------------------------------------------------------------

    def add_lane(
        self,
        name: str,
        *,
        weight: float = 1.0,
        capacity: int = 1_000,
    ) -> None:
        if name in self._lanes:
            raise WorkQueueError("lane exists", context={"lane": name})
        self._lanes[name] = Lane(name=name, weight=weight, capacity=capacity)

    def lanes(self) -> Tuple[str, ...]:
        return tuple(sorted(self._lanes))

    # ------------------------------------------------------------------
    # Enqueue / dequeue
    # ------------------------------------------------------------------

    def enqueue(
        self,
        lane: str,
        item_id: str,
        payload: Any = None,
        *,
        submitter: Optional[str] = None,
        deadline: Optional[float] = None,
    ) -> WorkItem:
        target = self._require(lane)
        if len(target.queue) >= target.capacity:
            raise LaneFullError(
                "lane at capacity",
                context={"lane": lane, "capacity": target.capacity},
            )
        if submitter is not None and self.per_submitter_cap is not None:
            held = self._submitter_counts.get(submitter, 0)
            if held >= self.per_submitter_cap:
                raise SubmitterCapError(
                    "submitter at fair-share cap",
                    context={"submitter": submitter, "cap": self.per_submitter_cap},
                )
        self._seq += 1
        item = WorkItem(
            item_id=item_id,
            payload=payload,
            enqueued_seq=self._seq,
            submitter=submitter,
            deadline=deadline,
        )
        target.queue.append(item)
        if submitter is not None:
            self._submitter_counts[submitter] = (
                self._submitter_counts.get(submitter, 0) + 1
            )
        return item

    def dequeue(self) -> Optional[Tuple[str, WorkItem]]:
        """Pick the next live item fairly.

        Returns ``(lane, item)`` or ``None`` only when every lane is empty,
        every queued item has expired, or the in-flight cap is reached.
        Fairness-credit advancement and expired-item retirement happen
        iteratively inside this call.
        """
        if len(self._in_flight_items) >= self.max_in_flight:
            return None

        now = self._now()
        while True:
            live = [ln for ln in self._lanes.values() if ln.queue]
            if not live:
                return None

            total_weight = sum(ln.weight for ln in live)
            for ln in live:
                ln.deficit += self.QUANTUM * (ln.weight / total_weight)

            # Highest deficit first; deterministic tie-break by name.
            live.sort(key=lambda ln: (-ln.deficit, ln.name))
            chosen = live[0]
            if chosen.deficit < self.QUANTUM:
                # Work exists, so advance another fairness round internally
                # instead of leaking a spurious "no work" result to callers.
                continue

            chosen.deficit -= self.QUANTUM
            item = chosen.queue.popleft()
            self._release_submitter(item)

            # Standard DRR discards leftover credit when a lane becomes idle.
            # Otherwise an old burst can buy priority for unrelated future work.
            if not chosen.queue:
                chosen.deficit = 0.0

            if item.is_expired(now):
                self._expired += 1
                continue

            self._in_flight_items[item.enqueued_seq] = (chosen.name, item)
            return chosen.name, item

    def complete(self, lane: str, item: WorkItem) -> None:
        """Mark the exact dequeued lane/item pair done.

        Completion is fail-closed: a duplicate completion, a foreign item,
        or the right item attributed to the wrong lane raises
        :class:`CompletionError` and leaves in-flight capacity unchanged.
        """
        active = self._in_flight_items.get(item.enqueued_seq)
        if active is None:
            self._completion_errors += 1
            raise CompletionError(
                "item is not in flight",
                context={
                    "lane": lane,
                    "item_id": item.item_id,
                    "enqueued_seq": item.enqueued_seq,
                },
            )

        active_lane, active_item = active
        if active_lane != lane or active_item is not item:
            self._completion_errors += 1
            raise CompletionError(
                "completion does not match active work",
                context={
                    "lane": lane,
                    "active_lane": active_lane,
                    "item_id": item.item_id,
                    "enqueued_seq": item.enqueued_seq,
                },
            )

        del self._in_flight_items[item.enqueued_seq]

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def depth(self, lane: Optional[str] = None) -> int:
        if lane is not None:
            return len(self._require(lane).queue)
        return sum(len(ln.queue) for ln in self._lanes.values())

    def stats(self) -> Dict[str, Any]:
        return {
            "lanes": self.report(),
            "in_flight": len(self._in_flight_items),
            "expired": self._expired,
            "completion_errors": self._completion_errors,
            "submitters": dict(self._submitter_counts),
        }

    def report(self) -> Dict[str, Dict[str, Any]]:
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
        for item in items:
            self._release_submitter(item)
        return items

    def _release_submitter(self, item: WorkItem) -> None:
        if item.submitter is None:
            return
        held = self._submitter_counts.get(item.submitter, 0)
        if held <= 1:
            self._submitter_counts.pop(item.submitter, None)
        else:
            self._submitter_counts[item.submitter] = held - 1

    def _require(self, lane: str) -> Lane:
        target = self._lanes.get(lane)
        if target is None:
            raise WorkQueueError("unknown lane", context={"lane": lane})
        return target
