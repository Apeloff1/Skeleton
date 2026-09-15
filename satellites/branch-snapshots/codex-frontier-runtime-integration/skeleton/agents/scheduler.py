"""The swarm scheduler.

A deterministic, synchronous-drive priority scheduler for agent work.
"Synchronous-drive" means the scheduler itself owns no threads: the host
calls :meth:`SwarmScheduler.run_once` (or :meth:`SwarmScheduler.run_until_idle`)
to pump the queue. This keeps the entire system testable without sleeps and
makes retry timing fully deterministic under a fake clock.

Features
--------
- Weighted priority classes (lower number = more urgent), FIFO within a class.
- Bounded in-flight window — submissions beyond the window stay queued
  (backpressure) rather than spawning unbounded concurrency.
- Retries with exponential backoff (base * 2^attempt, capped), then the
  dead-letter sink.
- Graceful drain: ``shutdown()`` stops accepting work and finishes in-flight
  tasks deterministically.
- Every transition appends to the activity ledger and emits an event.
"""

from __future__ import annotations

import heapq
import itertools
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from skeleton.agents.ledger import ActivityLedger
from skeleton.kernel.errors import SchedulingError, TaskDeadLetteredError
from skeleton.kernel.events import EventBus
from skeleton.kernel.ids import AgentId

TaskFn = Callable[[dict[str, Any]], dict[str, Any]]


class TaskState(str, Enum):
    QUEUED = "queued"
    IN_FLIGHT = "in_flight"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEAD_LETTERED = "dead_lettered"
    CANCELLED = "cancelled"


_counter = itertools.count()


@dataclass
class Task:
    """A unit of schedulable work."""

    name: str
    capability: str
    payload: dict[str, Any]
    run: TaskFn
    priority: int = 5  # 0 highest .. 9 lowest
    owner: AgentId | None = None
    max_retries: int = 3
    state: TaskState = TaskState.QUEUED
    attempts: int = 0
    result: dict[str, Any] | None = None
    error: str | None = None
    not_before: float = 0.0  # retry backoff gate
    task_id: str = field(default_factory=lambda: f"task_{next(_counter):08d}")
    submitted_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "capability": self.capability,
            "priority": self.priority,
            "state": self.state.value,
            "attempts": self.attempts,
            "result": self.result,
            "error": self.error,
            "submitted_at": self.submitted_at,
            "finished_at": self.finished_at,
        }


class SwarmScheduler:
    """Priority queue + retry engine + dead-letter sink for agent tasks."""

    def __init__(
        self,
        *,
        ledger: ActivityLedger | None = None,
        bus: EventBus | None = None,
        max_in_flight: int = 64,
        backoff_base: float = 0.5,
        backoff_cap: float = 30.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._ledger = ledger or ActivityLedger()
        self._bus = bus or EventBus()
        self._max_in_flight = max_in_flight
        self._backoff_base = backoff_base
        self._backoff_cap = backoff_cap
        self._clock = clock
        # Heap of (priority, sequence, task); sequence gives FIFO within a class.
        self._queue: list[tuple[int, int, Task]] = []
        self._sequence = itertools.count()
        self._tasks: dict[str, Task] = {}
        self._in_flight: set[str] = set()
        self._dead_letters: list[Task] = []
        self._accepting = True

    # -- submission ---------------------------------------------------------

    def submit(
        self,
        name: str,
        capability: str,
        payload: dict[str, Any],
        run: TaskFn,
        *,
        priority: int = 5,
        owner: AgentId | None = None,
        max_retries: int = 3,
    ) -> Task:
        """Enqueue a task. Raises once shutdown has begun."""
        if not self._accepting:
            raise SchedulingError(
                "Scheduler is draining and no longer accepts tasks",
                context={"task": name},
            )
        if not 0 <= priority <= 9:
            raise SchedulingError(
                "Priority must be within [0, 9]",
                context={"task": name, "priority": priority},
            )
        task = Task(
            name=name,
            capability=capability,
            payload=payload,
            run=run,
            priority=priority,
            owner=owner,
            max_retries=max_retries,
        )
        self._tasks[task.task_id] = task
        heapq.heappush(self._queue, (task.priority, next(self._sequence), task))
        self._bus.emit("agent.scheduler.submitted", task.to_dict())
        return task

    def cancel(self, task_id: str) -> Task:
        task = self._require(task_id)
        if task.state is TaskState.QUEUED:
            task.state = TaskState.CANCELLED
            task.finished_at = self._clock()
            self._bus.emit("agent.scheduler.cancelled", task.to_dict())
        return task

    # -- execution ------------------------------------------------------------

    def run_once(self) -> Task | None:
        """Run the head-of-queue task if the in-flight window permits."""
        if len(self._in_flight) >= self._max_in_flight:
            return None
        task = self._next_runnable()
        if task is None:
            return None
        self._in_flight.add(task.task_id)
        task.state = TaskState.IN_FLIGHT
        task.attempts += 1
        self._bus.emit("agent.scheduler.started", {**task.to_dict(), "attempt": task.attempts})
        try:
            result = task.run(task.payload)
        except Exception as exc:  # noqa: BLE001 - failures are first-class data here
            self._handle_failure(task, exc)
        else:
            task.state = TaskState.SUCCEEDED
            task.result = result
            task.finished_at = self._clock()
            self._ledger.append(
                task.owner or AgentId.new(),
                f"task.{task.capability}",
                {"task": task.name, "attempts": task.attempts},
                outcome="success",
            )
            self._bus.emit("agent.scheduler.succeeded", task.to_dict())
        finally:
            self._in_flight.discard(task.task_id)
        return task

    def run_until_idle(self, *, max_iterations: int = 10_000) -> list[Task]:
        """Pump the queue until no runnable work remains. Returns tasks run."""
        ran: list[Task] = []
        for _ in range(max_iterations):
            task = self.run_once()
            if task is None:
                break
            ran.append(task)
        return ran

    def _next_runnable(self) -> Task | None:
        now = self._clock()
        skipped: list[tuple[int, int, Task]] = []
        chosen: Task | None = None
        while self._queue:
            item = heapq.heappop(self._queue)
            task = item[2]
            if task.state is TaskState.CANCELLED:
                continue
            if task.not_before > now:
                skipped.append(item)
                continue
            chosen = task
            break
        for item in skipped:
            heapq.heappush(self._queue, item)
        return chosen

    def _handle_failure(self, task: Task, exc: Exception) -> None:
        task.error = f"{type(exc).__name__}: {exc}"
        if task.attempts <= task.max_retries:
            delay = min(self._backoff_base * (2 ** (task.attempts - 1)), self._backoff_cap)
            task.state = TaskState.QUEUED
            task.not_before = self._clock() + delay
            heapq.heappush(self._queue, (task.priority, next(self._sequence), task))
            self._bus.emit(
                "agent.scheduler.retry_scheduled",
                {**task.to_dict(), "retry_in_seconds": delay},
            )
        else:
            task.state = TaskState.DEAD_LETTERED
            task.finished_at = self._clock()
            self._dead_letters.append(task)
            self._ledger.append(
                task.owner or AgentId.new(),
                f"task.{task.capability}",
                {"task": task.name, "attempts": task.attempts, "error": task.error},
                outcome="failure",
            )
            self._bus.emit("agent.scheduler.dead_lettered", task.to_dict())

    # -- lifecycle -------------------------------------------------------------

    def shutdown(self, *, drain: bool = True) -> list[Task]:
        """Stop accepting work; optionally run everything queued to completion."""
        self._accepting = False
        drained: list[Task] = []
        if drain:
            drained = self.run_until_idle()
        self._bus.emit("agent.scheduler.shutdown", {"drained": len(drained)})
        return drained

    @property
    def accepting(self) -> bool:
        return self._accepting

    # -- introspection -----------------------------------------------------------

    def _require(self, task_id: str) -> Task:
        task = self._tasks.get(task_id)
        if task is None:
            raise SchedulingError(
                f"Unknown task {task_id!r}", context={"task_id": task_id}
            )
        return task

    def get(self, task_id: str) -> Task:
        return self._require(task_id)

    def dead_letters(self) -> list[Task]:
        return list(self._dead_letters)

    def requeue_dead_letter(self, task_id: str) -> Task:
        """Move a dead-lettered task back to the queue for a fresh run."""
        task = self._require(task_id)
        if task.state is not TaskState.DEAD_LETTERED:
            raise TaskDeadLetteredError(
                "Only dead-lettered tasks can be requeued",
                context={"task_id": task_id, "state": task.state.value},
            )
        self._dead_letters.remove(task)
        task.state = TaskState.QUEUED
        task.attempts = 0
        task.error = None
        task.not_before = 0.0
        heapq.heappush(self._queue, (task.priority, next(self._sequence), task))
        self._bus.emit("agent.scheduler.requeued", task.to_dict())
        return task

    def pending(self) -> list[Task]:
        return sorted(
            (t for _, _, t in self._queue if t.state is TaskState.QUEUED),
            key=lambda t: (t.priority, t.submitted_at),
        )

    def stats(self) -> dict[str, Any]:
        states: dict[str, int] = {}
        for task in self._tasks.values():
            states[task.state.value] = states.get(task.state.value, 0) + 1
        return {
            "accepting": self._accepting,
            "queued": len(self._queue),
            "in_flight": len(self._in_flight),
            "max_in_flight": self._max_in_flight,
            "dead_letters": len(self._dead_letters),
            "by_state": states,
        }
