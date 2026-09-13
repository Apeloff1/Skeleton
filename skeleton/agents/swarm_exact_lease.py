"""Exact-task leasing for brokers that must not consume unrelated queued work."""
from __future__ import annotations
from contextlib import nullcontext
from dataclasses import replace
from skeleton.agents.swarm_runtime import LeaseError, SwarmRuntime, SwarmTask, TaskState


def lease_exact(runtime: SwarmRuntime, worker_id: str, task_id: str) -> SwarmTask:
    lock = getattr(runtime, "_lock", None)
    context = lock if lock is not None else nullcontext()
    with context:
        worker = runtime._workers.get(worker_id.strip())
        if worker is None: raise LeaseError(f"unknown worker: {worker_id}")
        if worker.available <= 0: raise LeaseError(f"worker has no available capacity: {worker_id}")
        task = runtime._tasks.get(task_id.strip())
        if task is None or task.state is not TaskState.QUEUED: raise LeaseError(f"task is not queued: {task_id}")
        if not task.required_capabilities.issubset(worker.capabilities): raise LeaseError(f"worker lacks required capabilities: {worker_id}")
        updated = replace(task, state=TaskState.LEASED, attempts=task.attempts+1, leased_to=worker.id, lease_deadline=runtime._clock()+runtime.default_lease_seconds)
        runtime._replace(task, updated); worker.active.add(task.id); worker.accepted += 1; worker.last_seen = runtime._clock(); runtime._event("task.leased", task.id)
        return updated
