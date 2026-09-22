"""Resident-state garbage collection for bounded swarm runtimes."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_runtime import SwarmRuntime, TaskState

TERMINAL = {TaskState.SUCCEEDED.value, TaskState.DEAD.value, TaskState.CANCELLED.value, TaskState.FAILED.value}


@dataclass(frozen=True, slots=True)
class GCResult:
    before: int
    after: int
    removed: int
    retained_terminal: int


def compact_runtime(runtime: SwarmRuntime, *, keep_terminal: int = 10_000) -> tuple[SwarmRuntime, GCResult]:
    """Rebuild runtime with bounded terminal history while preserving hardening."""
    if keep_terminal < 0:
        raise ValueError("keep_terminal must be non-negative")
    state = runtime.export_state()
    tasks = list(state.get("tasks", []))
    live = [task for task in tasks if task.get("state") not in TERMINAL]
    terminal = [task for task in tasks if task.get("state") in TERMINAL]
    retained = terminal[-keep_terminal:] if keep_terminal else []
    state["tasks"] = live + retained
    runtime_type = HardenedSwarmRuntime if isinstance(runtime, HardenedSwarmRuntime) else SwarmRuntime
    rebuilt = runtime_type.from_state(state, requeue_leased=False)
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
