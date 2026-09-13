"""Retention and compaction policy for resident swarm task history."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from skeleton.agents.swarm_runtime import SwarmRuntime, TaskState


TERMINAL_STATES = frozenset({TaskState.SUCCEEDED, TaskState.DEAD, TaskState.CANCELLED, TaskState.FAILED})


@dataclass(frozen=True, slots=True)
class PrunePlan:
    removable: tuple[str, ...]
    retained: int
    terminal: int


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    max_terminal_tasks: int = 10_000

    def __post_init__(self) -> None:
        if self.max_terminal_tasks < 0:
            raise ValueError("max_terminal_tasks must be non-negative")

    def plan(self, runtime: SwarmRuntime) -> PrunePlan:
        terminal = [task.id for task in runtime.tasks() if task.state in TERMINAL_STATES]
        excess = max(0, len(terminal) - self.max_terminal_tasks)
        return PrunePlan(tuple(terminal[:excess]), len(terminal) - excess, len(terminal))


def prune_terminal(runtime: SwarmRuntime, task_ids: Iterable[str]) -> int:
    """Prune selected terminal tasks using the runtime's explicit forget seam."""
    removed = 0
    for task_id in task_ids:
        forget = getattr(runtime, "forget", None)
        if forget is None:
            raise RuntimeError("runtime does not expose terminal task forgetting")
        if forget(task_id):
            removed += 1
    return removed
