"""Compensating rollback for exact swarm leases that fail policy publication."""

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


def _finite_clock(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LeaseError("clock must be a finite number")
    normalized = float(value)
    if not isfinite(normalized):
        raise LeaseError("clock must be a finite number")
    return normalized


def rollback_exact_lease(runtime: SwarmRuntime, worker_id: str, task_id: str) -> SwarmTask:
    """Return an owned lease to the queue without consuming an attempt or failure."""
    lock = getattr(runtime, "_lock", None)
    context = lock if lock is not None else nullcontext()
    with context:
        worker_id = _identifier(worker_id, "worker_id")
        task_id = _identifier(task_id, "task_id")
        worker = runtime._workers.get(worker_id)
        if worker is None:
            raise LeaseError(f"unknown worker: {worker_id}")
        task = runtime._tasks.get(task_id)
        if task is None or task.state is not TaskState.LEASED:
            raise LeaseError(f"task is not leased: {task_id}")
        if task.leased_to != worker_id:
            raise LeaseError(f"task {task_id} is leased to {task.leased_to}")
        if task.attempts < 1:
            raise LeaseError(f"leased task has invalid attempt count: {task_id}")
        if worker.accepted < 1:
            raise LeaseError(f"worker has invalid accepted count: {worker_id}")

        # Sample and validate all fallible external state before mutating accounting.
        now = _finite_clock(runtime._clock())
        updated = replace(
            task,
            state=TaskState.QUEUED,
            attempts=task.attempts - 1,
            leased_to=None,
            lease_deadline=None,
        )
        runtime._replace(task, updated)
        worker.active.discard(task_id)
        worker.accepted -= 1
        runtime._requeue(task_id)
        runtime._events.append((now, "task.lease_rolled_back", task_id))
        return updated
