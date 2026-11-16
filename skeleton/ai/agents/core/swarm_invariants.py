"""Cross-structure invariant auditing for swarm runtime state."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.automation.agents.swarm_runtime import SwarmRuntime, TaskState


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
    singletons: dict[str, str] = {}
    for task in tasks:
        if task.state is TaskState.LEASED:
            leased_ids.add(task.id)
        if task.effect_uncertain and (not runtime.fenced or task.state is not TaskState.FAILED):
            errors.append(f"invalid uncertain state:{task.id}")
        if any(dep not in task_map for dep in task.dependencies):
            errors.append(f"unknown task dependency:{task.id}")
        if task.state is TaskState.LEASED or task.effect_uncertain:
            if task.wait_intent_sha256 is not None and task.wake_receipt_sha256 is None:
                errors.append(f"unopened wait owns a slot:{task.id}")
            if task.singleton_scope_sha256 is not None:
                if task.singleton_scope_sha256 in singletons:
                    errors.append(f"duplicate singleton occupancy:{task.id}")
                singletons[task.singleton_scope_sha256] = task.id
            if runtime.fenced and not task.lease_token:
                errors.append(f"fenced task missing token:{task.id}")
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

    if singletons != runtime._singleton_holders:
        errors.append("singleton occupancy index mismatch")
    delegated = {worker.id: 0 for worker in workers}
    for worker in workers:
        if worker.parent_id is not None:
            parent = worker_map.get(worker.parent_id)
            if parent is None or not runtime.fenced:
                errors.append(f"invalid virtual parent:{worker.id}")
            else:
                delegated[parent.id] += worker.capacity
                if not worker.capabilities <= parent.capabilities:
                    errors.append(f"virtual capability escalation:{worker.id}")
                try:
                    runtime.worker_lineage(worker.id)
                except Exception:
                    errors.append(f"invalid virtual lineage:{worker.id}")
    for worker in workers:
        if worker.delegated_capacity != delegated[worker.id]:
            errors.append(f"virtual capacity accounting mismatch:{worker.id}")
        if len(worker.active) + delegated[worker.id] > worker.capacity:
            errors.append(f"worker over capacity:{worker.id}")
        for task_id in worker.active:
            task = task_map.get(task_id)
            if task is None:
                errors.append(f"worker references missing task:{worker.id}:{task_id}")
            elif task.state is not TaskState.LEASED and not task.effect_uncertain:
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
