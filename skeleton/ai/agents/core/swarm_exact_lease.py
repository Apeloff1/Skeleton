"""Exact-task leasing for brokers that must not consume unrelated queued work."""
from __future__ import annotations

from contextlib import nullcontext
from dataclasses import replace
from math import isfinite

from skeleton.agents.swarm_runtime import LeaseError, SwarmRuntime, SwarmTask, TaskState


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise LeaseError(f"{label} must be a string")
    value = value.strip()
    if not value:
        raise LeaseError(f"{label} must not be empty")
    return value


def _finite_number(value: object, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LeaseError(f"{label} must be a finite number")
    normalized = float(value)
    if not isfinite(normalized) or (positive and normalized <= 0):
        qualifier = "positive finite" if positive else "finite"
        raise LeaseError(f"{label} must be a {qualifier} number")
    return normalized


def lease_exact(runtime: SwarmRuntime, worker_id: str, task_id: str) -> SwarmTask:
    """Lease exactly one queued task without post-mutation failure points."""
    lock = getattr(runtime, "_lock", None)
    context = lock if lock is not None else nullcontext()
    with context:
        worker_id = _identifier(worker_id, "worker_id")
        task_id = _identifier(task_id, "task_id")
        worker = runtime._workers.get(worker_id)
        if worker is None:
            raise LeaseError(f"unknown worker: {worker_id}")
        if worker.available <= 0:
            raise LeaseError(f"worker has no available capacity: {worker_id}")
        task = runtime._tasks.get(task_id)
        if task is None or task.state is not TaskState.QUEUED:
            raise LeaseError(f"task is not queued: {task_id}")
        if not task.required_capabilities.issubset(worker.capabilities):
            raise LeaseError(f"worker lacks required capabilities: {worker_id}")

        # Sample and validate all fallible external state before mutating accounting.
        now = _finite_number(runtime._clock(), "clock")
        lease_seconds = _finite_number(
            runtime.default_lease_seconds,
            "default_lease_seconds",
            positive=True,
        )
        deadline = now + lease_seconds
        if not isfinite(deadline):
            raise LeaseError("lease deadline must be finite")
        updated = replace(
            task,
            state=TaskState.LEASED,
            attempts=task.attempts + 1,
            leased_to=worker.id,
            lease_deadline=deadline,
        )

        runtime._replace(task, updated)
        worker.active.add(task.id)
        worker.accepted += 1
        worker.last_seen = now
        runtime._events.append((now, "task.leased", task.id))
        return updated
