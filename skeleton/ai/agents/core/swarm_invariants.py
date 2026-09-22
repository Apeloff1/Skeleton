"""Cross-structure invariant auditing for swarm runtime state."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.agents.swarm_runtime import SwarmRuntime, TaskState


@dataclass(frozen=True, slots=True)
class InvariantReport:
    ok: bool
    errors: tuple[str, ...]
    task_count: int
    worker_count: int


def audit(runtime: SwarmRuntime) -> InvariantReport:
    errors: list[str] = []
    tasks = runtime.tasks()
    workers = runtime.workers()
    task_map = {task.id: task for task in tasks}
    worker_map = {worker.id: worker for worker in workers}

    if len(task_map) != len(tasks):
        errors.append("duplicate task ids")
    if len(worker_map) != len(workers):
        errors.append("duplicate worker ids")

    leased_ids: set[str] = set()
    for task in tasks:
        if task.state is TaskState.LEASED:
            leased_ids.add(task.id)
            if not task.leased_to:
                errors.append(f"leased task missing worker:{task.id}")
                continue
            worker = worker_map.get(task.leased_to)
            if worker is None:
                errors.append(f"leased task worker missing:{task.id}")
            elif task.id not in worker.active:
                errors.append(f"leased task absent from worker active set:{task.id}")
            if task.lease_deadline is None:
                errors.append(f"leased task missing deadline:{task.id}")
        else:
            if task.leased_to is not None:
                errors.append(f"non-leased task has owner:{task.id}")
            if task.lease_deadline is not None:
                errors.append(f"non-leased task has deadline:{task.id}")

    for worker in workers:
        if len(worker.active) > worker.capacity:
            errors.append(f"worker over capacity:{worker.id}")
        for task_id in worker.active:
            task = task_map.get(task_id)
            if task is None:
                errors.append(f"worker references missing task:{worker.id}:{task_id}")
            elif task.state is not TaskState.LEASED:
                errors.append(f"worker references non-leased task:{worker.id}:{task_id}")
            elif task.leased_to != worker.id:
                errors.append(f"worker ownership mismatch:{worker.id}:{task_id}")

    snapshot = runtime.snapshot()
    counted = {
        TaskState.QUEUED: snapshot.queued,
        TaskState.LEASED: snapshot.leased,
        TaskState.SUCCEEDED: snapshot.succeeded,
        TaskState.FAILED: snapshot.failed,
        TaskState.DEAD: snapshot.dead,
        TaskState.CANCELLED: snapshot.cancelled,
    }
    for state, expected in counted.items():
        actual = sum(task.state is state for task in tasks)
        if actual != expected:
            errors.append(f"state count mismatch:{state.value}:{expected}!={actual}")

    if snapshot.leased != len(leased_ids):
        errors.append("leased snapshot count mismatch")
    return InvariantReport(not errors, tuple(errors), len(tasks), len(workers))
