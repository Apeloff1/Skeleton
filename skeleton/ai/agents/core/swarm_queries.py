"""Bounded query projections for operator and API consumers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from skeleton.agents.swarm_runtime import SwarmRuntime, SwarmTask, TaskState


@dataclass(frozen=True, slots=True)
class TaskPage:
    items: tuple[SwarmTask, ...]
    total: int
    offset: int
    limit: int


def query_tasks(
    runtime: SwarmRuntime,
    *,
    states: Iterable[TaskState] | None = None,
    capability: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> TaskPage:
    if offset < 0:
        raise ValueError("offset must be non-negative")
    if not 1 <= limit <= 10_000:
        raise ValueError("limit must be between 1 and 10000")
    allowed = None if states is None else frozenset(states)
    items = []
    for task in runtime.tasks():
        if allowed is not None and task.state not in allowed:
            continue
        if capability is not None and capability not in task.required_capabilities:
            continue
        items.append(task)
    items.sort(key=lambda task: (task.priority, task.id))
    total = len(items)
    return TaskPage(tuple(items[offset:offset + limit]), total, offset, limit)
