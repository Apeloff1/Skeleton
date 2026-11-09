"""Deadline scheduler for the kernel — run-the-right-thing-on-time.

The bus tells you *what* happened; the scheduler decides *when* work
runs. This module is a dependency-aware, deadline-driven scheduler for
agent tasks:

- Tasks carry an earliest-start, a hard deadline, an estimated duration,
  and dependencies on other tasks.
- :meth:`DeadlineScheduler.schedule` performs an earliest-deadline-first
  pass over the feasible set, detecting dependency cycles and provably
  unschedulable tasks instead of silently dropping them.
- :meth:`next_batch` hands the dispatcher the set of tasks that can run
  in parallel *right now* without violating any deadline.

The point is not throughput — it is guarantees. Anything the scheduler
admits is admitted with proof its deadline is still reachable.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .errors import KernelError


class SchedulingError(KernelError):
    code = "KRN.SCHEDULING"


class CycleError(SchedulingError):
    code = "KRN.SCHED_CYCLE"


class UnschedulableError(SchedulingError):
    code = "KRN.SCHED_INFEASIBLE"


@dataclass(frozen=True)
class ScheduledTask:
    task_id: str
    earliest_start: float
    deadline: float
    duration: float
    depends_on: Tuple[str, ...] = ()
    priority: int = 0

    def validate(self, now: float) -> None:
        if self.duration <= 0:
            raise UnschedulableError(
                "task duration must be positive",
                context={"task": self.task_id, "duration": self.duration},
            )
        if self.earliest_start + self.duration > self.deadline:
            raise UnschedulableError(
                "task cannot finish before its own deadline",
                context={
                    "task": self.task_id,
                    "earliest_start": self.earliest_start,
                    "deadline": self.deadline,
                    "duration": self.duration,
                },
            )
        if self.deadline < now:
            raise UnschedulableError(
                "task deadline already passed",
                context={"task": self.task_id, "deadline": self.deadline, "now": now},
            )


class DeadlineScheduler:
    """Earliest-deadline-first scheduler with dependency awareness."""

    def __init__(self) -> None:
        self._tasks: Dict[str, ScheduledTask] = {}
        self._completed: Set[str] = set()

    # ------------------------------------------------------------------
    # Intake
    # ------------------------------------------------------------------

    def add(self, task: ScheduledTask) -> None:
        task.validate(now=time.time())
        if task.task_id in self._tasks:
            raise SchedulingError(
                "task id already registered",
                context={"task": task.task_id},
            )
        missing = [d for d in task.depends_on
                   if d not in self._tasks and d not in self._completed]
        if missing:
            raise SchedulingError(
                "task depends on unknown tasks",
                context={"task": task.task_id, "missing": tuple(missing)},
            )
        self._tasks[task.task_id] = task
        self._check_cycle(task.task_id)

    def _check_cycle(self, start: str) -> None:
        stack, seen, path = [start], set(), []
        while stack:
            node = stack.pop()
            if node in path:
                raise CycleError(
                    "dependency cycle detected",
                    context={"cycle": tuple(path[path.index(node):] + [node])},
                )
            if node in seen:
                continue
            seen.add(node)
            path.append(node)
            t = self._tasks.get(node)
            if t:
                stack.extend(d for d in t.depends_on if d in self._tasks)
            path.pop()

    # ------------------------------------------------------------------
    # Feasibility
    # ------------------------------------------------------------------

    def _feasible(self, task: ScheduledTask, now: float,
                  completion: Dict[str, float]) -> Optional[float]:
        """Return earliest feasible start, or None if unreachable."""
        start = max(task.earliest_start, now)
        for dep in task.depends_on:
            if dep in self._completed:
                continue
            dep_done = completion.get(dep)
            if dep_done is None:
                return None  # dependency itself infeasible
            start = max(start, dep_done)
        if start + task.duration > task.deadline:
            return None
        return start

    def schedule(self, *, now: Optional[float] = None) -> List[Tuple[str, float, float]]:
        """Plan all pending tasks. Returns [(task_id, start, finish)] in
        start order. Raises :class:`UnschedulableError` listing every task
        that cannot meet its deadline."""
        now = time.time() if now is None else now
        pending = [t for t in self._tasks.values() if t.task_id not in self._completed]
        pending.sort(key=lambda t: (t.deadline, -t.priority, t.task_id))

        completion: Dict[str, float] = {}
        plan: List[Tuple[str, float, float]] = []
        infeasible: List[str] = []

        # iterate until fixpoint: completing tasks unlocks their dependents
        progressed = True
        remaining = list(pending)
        while remaining and progressed:
            progressed = False
            still: List[ScheduledTask] = []
            for task in remaining:
                start = self._feasible(task, now, completion)
                if start is None:
                    # might just be waiting on an unscheduled dep
                    deps_pending = [d for d in task.depends_on
                                    if d not in self._completed and d not in completion]
                    if deps_pending:
                        still.append(task)
                    else:
                        infeasible.append(task.task_id)
                    continue
                finish = start + task.duration
                completion[task.task_id] = finish
                plan.append((task.task_id, start, finish))
                progressed = True
            remaining = still

        infeasible.extend(t.task_id for t in remaining)
        if infeasible:
            raise UnschedulableError(
                "one or more tasks cannot meet their deadlines",
                context={"infeasible": tuple(sorted(infeasible))},
            )
        plan.sort(key=lambda p: (p[1], p[0]))
        return plan

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def next_batch(self, *, now: Optional[float] = None,
                   limit: Optional[int] = None) -> List[str]:
        """Task ids whose dependencies are complete and whose windows are open,
        earliest deadline first."""
        now = time.time() if now is None else now
        ready = [
            t for t in self._tasks.values()
            if t.task_id not in self._completed
            and t.earliest_start <= now
            and all(d in self._completed for d in t.depends_on)
        ]
        ready.sort(key=lambda t: (t.deadline, -t.priority, t.task_id))
        ids = [t.task_id for t in ready]
        return ids[:limit] if limit else ids

    def complete(self, task_id: str) -> None:
        if task_id not in self._tasks:
            raise SchedulingError("unknown task", context={"task": task_id})
        self._completed.add(task_id)

    def pending(self) -> Tuple[str, ...]:
        return tuple(sorted(k for k in self._tasks if k not in self._completed))
