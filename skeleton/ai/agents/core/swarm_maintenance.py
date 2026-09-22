"""Maintenance operations that compact swarm state through public snapshot seams."""

from __future__ import annotations

from typing import Any

from skeleton.agents.swarm_retention import RetentionPolicy, TERMINAL_STATES
from skeleton.agents.swarm_runtime import SwarmRuntime, TaskState
from skeleton.agents.swarm_snapshot import normalize_snapshot


def compact_state(runtime: SwarmRuntime, *, max_terminal_tasks: int = 10_000) -> dict[str, Any]:
    """Create a compact restorable snapshot without mutating the live runtime."""
    policy = RetentionPolicy(max_terminal_tasks=max_terminal_tasks)
    plan = policy.plan(runtime)
    removable = set(plan.removable)
    state = normalize_snapshot(runtime.export_state())
    state["tasks"] = [task for task in state["tasks"] if str(task["id"]) not in removable]
    state["maintenance"] = {
        "pruned_terminal_tasks": len(removable),
        "retained_terminal_tasks": plan.retained,
    }
    return state


def compact_runtime(runtime: SwarmRuntime, *, max_terminal_tasks: int = 10_000) -> SwarmRuntime:
    """Return a new runtime restored from compacted state."""
    state = compact_state(runtime, max_terminal_tasks=max_terminal_tasks)
    return SwarmRuntime.from_state(state)
