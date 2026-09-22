"""Atomic preflight and batch admission for swarm tasks."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from skeleton.agents.swarm_runtime import AdmissionError, SwarmRuntime, SwarmTask


@dataclass(frozen=True, slots=True)
class BatchResult:
    task_ids: tuple[str, ...]
    admitted: int


def preflight(runtime: SwarmRuntime, tasks: Iterable[SwarmTask]) -> tuple[SwarmTask, ...]:
    batch = tuple(tasks)
    ids = [task.id.strip() for task in batch]
    if any(not task_id for task_id in ids):
        raise AdmissionError("task id must not be empty")
    if len(ids) != len(set(ids)):
        raise AdmissionError("duplicate task id inside batch")
    if len(runtime.tasks()) + len(batch) > runtime.max_tasks:
        raise AdmissionError("batch exceeds runtime task capacity")
    for task, task_id in zip(batch, ids):
        if runtime.task(task_id) is not None:
            raise AdmissionError(f"duplicate task id: {task_id}")
        if task.max_attempts < 1:
            raise AdmissionError("max_attempts must be positive")
    return batch


def submit_batch(runtime: SwarmRuntime, tasks: Iterable[SwarmTask]) -> BatchResult:
    """Admit a complete batch atomically when the runtime exposes native support."""
    batch = tuple(tasks)
    native = getattr(runtime, "submit_many", None)
    if callable(native):
        admitted = tuple(task.id for task in native(batch))
        return BatchResult(admitted, len(admitted))

    checked = preflight(runtime, batch)
    admitted = tuple(runtime.submit(task).id for task in checked)
    return BatchResult(admitted, len(admitted))
