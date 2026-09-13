"""Resident-state garbage collection for bounded swarm runtimes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from skeleton.agents.swarm_runtime import SwarmRuntime, TaskState

TERMINAL = {TaskState.SUCCEEDED.value, TaskState.DEAD.value, TaskState.CANCELLED.value, TaskState.FAILED.value}


@dataclass(frozen=True, slots=True)
class GCResult:
    before: int
    after: int
    removed: int
    retained_terminal: int


def compact_runtime(runtime: SwarmRuntime, *, keep_terminal: int = 10_000) -> tuple[SwarmRuntime, GCResult]:
    """Create an equivalent runtime with bounded terminal history.

    Live/queued tasks and worker accounting are preserved. Terminal tasks are
    retained newest-first according to resident task order. This rebuilds the
    runtime rather than mutating private indices in place, eliminating stale
    heap references and reclaiming admission capacity deterministically.
    """
    if keep_terminal < 0:
        raise ValueError("keep_terminal must be non-negative")
    state = runtime.export_state()
    tasks = list(state.get("tasks", []))
    live = [task for task in tasks if task.get("state") not in TERMINAL]
    terminal = [task for task in tasks if task.get("state") in TERMINAL]
    retained = terminal[-keep_terminal:] if keep_terminal else []
    state["tasks"] = live + retained
    rebuilt = SwarmRuntime.from_state(state, requeue_leased=False)
    before = len(tasks)
    after = len(live) + len(retained)
    return rebuilt, GCResult(before, after, before - after, len(retained))


def capacity(runtime: SwarmRuntime) -> dict[str, int]:
    resident = len(runtime.tasks())
    return {
        "resident": resident,
        "maximum": runtime.max_tasks,
        "available": max(0, runtime.max_tasks - resident),
    }
