"""Graceful worker drain planning for maintenance and rolling upgrades."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.agents.swarm_runtime import SwarmRuntime, TaskState


@dataclass(frozen=True, slots=True)
class DrainPlan:
    worker_id: str
    active_tasks: tuple[str, ...]
    requeueable: tuple[str, ...]
    blocked: tuple[str, ...]


def plan_drain(runtime: SwarmRuntime, worker_id: str) -> DrainPlan:
    worker = runtime.worker(worker_id)
    if worker is None:
        raise KeyError(worker_id)
    active = tuple(sorted(worker.active))
    requeueable: list[str] = []
    blocked: list[str] = []
    for task_id in active:
        task = runtime.task(task_id)
        if task is None or task.state is not TaskState.LEASED:
            continue
        if task.attempts < task.max_attempts:
            requeueable.append(task_id)
        else:
            blocked.append(task_id)
    return DrainPlan(worker_id, active, tuple(requeueable), tuple(blocked))


def drain(runtime: SwarmRuntime, worker_id: str, *, force: bool = False) -> DrainPlan:
    plan = plan_drain(runtime, worker_id)
    if plan.blocked and not force:
        return plan
    runtime.unregister_worker(worker_id, requeue=not force)
    return plan
