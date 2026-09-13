"""Strict validation for swarm snapshots before runtime restoration."""

from __future__ import annotations

from typing import Mapping

from skeleton.agents.swarm_runtime import TaskState


def validate_restore_state(state: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(state, Mapping):
        raise ValueError("runtime state must be a mapping")
    version = int(state.get("version", 1))
    if version != 1:
        raise ValueError(f"unsupported runtime state version: {version}")
    config_raw = state.get("config", {})
    if not isinstance(config_raw, Mapping):
        raise ValueError("invalid runtime state config")
    config = dict(config_raw)
    max_tasks = int(config.get("max_tasks", 100_000))
    max_workers = int(config.get("max_workers", 10_000))
    default_lease = float(config.get("default_lease_seconds", 30.0))
    max_lease = float(config.get("max_lease_seconds", 86_400.0))
    if max_tasks < 1 or max_workers < 1:
        raise ValueError("runtime capacities must be positive")
    if default_lease <= 0 or max_lease <= 0 or default_lease > max_lease:
        raise ValueError("invalid lease configuration")

    tasks_raw = state.get("tasks", [])
    workers_raw = state.get("workers", [])
    counters_raw = state.get("counters", {})
    if not isinstance(tasks_raw, list) or not isinstance(workers_raw, list):
        raise ValueError("tasks and workers must be lists")
    if not isinstance(counters_raw, Mapping):
        raise ValueError("counters must be a mapping")
    if len(tasks_raw) > max_tasks:
        raise ValueError("snapshot exceeds max_tasks")
    if len(workers_raw) > max_workers:
        raise ValueError("snapshot exceeds max_workers")

    task_ids: set[str] = set()
    worker_ids: set[str] = set()
    leased: dict[str, str] = {}
    for raw in tasks_raw:
        if not isinstance(raw, Mapping):
            raise ValueError("invalid task record")
        task_id = str(raw.get("id", "")).strip()
        if not task_id:
            raise ValueError("task id must not be empty")
        if task_id in task_ids:
            raise ValueError(f"duplicate task id in snapshot: {task_id}")
        task_ids.add(task_id)
        max_attempts = int(raw.get("max_attempts", 3))
        attempts = int(raw.get("attempts", 0))
        if max_attempts < 1 or attempts < 0:
            raise ValueError(f"invalid attempts for task: {task_id}")
        state_value = TaskState(str(raw.get("state", TaskState.QUEUED.value)))
        owner = raw.get("leased_to")
        if state_value is TaskState.LEASED:
            if not owner:
                raise ValueError(f"leased task missing owner: {task_id}")
            leased[task_id] = str(owner).strip()
        elif owner is not None:
            raise ValueError(f"non-leased task has owner: {task_id}")

    for raw in workers_raw:
        if not isinstance(raw, Mapping):
            raise ValueError("invalid worker record")
        worker_id = str(raw.get("id", "")).strip()
        if not worker_id:
            raise ValueError("worker id must not be empty")
        if worker_id in worker_ids:
            raise ValueError(f"duplicate worker id in snapshot: {worker_id}")
        worker_ids.add(worker_id)
        capacity = int(raw.get("capacity", 1))
        if capacity < 1:
            raise ValueError(f"invalid worker capacity: {worker_id}")
        active = {str(item) for item in raw.get("active", ())}
        if len(active) > capacity:
            raise ValueError(f"worker active set exceeds capacity: {worker_id}")
        for task_id in active:
            if task_id not in leased:
                raise ValueError(f"worker references non-leased task: {task_id}")
            if leased[task_id] != worker_id:
                raise ValueError(f"worker does not own active task: {task_id}")

    missing_workers = sorted({owner for owner in leased.values() if owner not in worker_ids})
    if missing_workers:
        raise ValueError(f"leased task references missing worker: {missing_workers[0]}")

    clean = dict(state)
    clean["version"] = version
    clean["config"] = config
    clean["tasks"] = [dict(item) for item in tasks_raw]
    clean["workers"] = [dict(item) for item in workers_raw]
    clean["counters"] = dict(counters_raw)
    return clean
