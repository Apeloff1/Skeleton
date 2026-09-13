"""Strict validation for swarm snapshots before runtime restoration."""

from __future__ import annotations

from math import isfinite
from typing import Mapping

from skeleton.agents.swarm_runtime import TaskState

_COUNTERS = (
    "submitted",
    "retries",
    "expired_leases",
    "lease_renewals",
    "heartbeats",
    "revived",
)
_WORKER_COUNTERS = ("accepted", "completed", "failed", "renewals", "heartbeats")


def _nonnegative_int(value: object, label: str) -> int:
    result = int(value)
    if result < 0:
        raise ValueError(f"{label} must be non-negative")
    return result


def validate_restore_state(state: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(state, Mapping):
        raise ValueError("runtime state must be a mapping")
    version = int(state.get("version", 1))
    if version != 1:
        raise ValueError(f"unsupported runtime state version: {version}")
    config_raw = state.get("config", {})
    if not isinstance(config_raw, Mapping):
        raise ValueError("invalid runtime state config")
    max_tasks = int(config_raw.get("max_tasks", 100_000))
    max_workers = int(config_raw.get("max_workers", 10_000))
    default_lease = float(config_raw.get("default_lease_seconds", 30.0))
    max_lease = float(config_raw.get("max_lease_seconds", 86_400.0))
    if max_tasks < 1 or max_workers < 1:
        raise ValueError("runtime capacities must be positive")
    if not isfinite(default_lease) or not isfinite(max_lease):
        raise ValueError("lease configuration must be finite")
    if default_lease <= 0 or max_lease <= 0 or default_lease > max_lease:
        raise ValueError("invalid lease configuration")
    config = dict(config_raw)
    config.update(
        {
            "max_tasks": max_tasks,
            "max_workers": max_workers,
            "default_lease_seconds": default_lease,
            "max_lease_seconds": max_lease,
        }
    )

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
    clean_tasks: list[dict[str, object]] = []
    for raw in tasks_raw:
        if not isinstance(raw, Mapping):
            raise ValueError("invalid task record")
        task_id = str(raw.get("id", "")).strip()
        if not task_id:
            raise ValueError("task id must not be empty")
        if task_id in task_ids:
            raise ValueError(f"duplicate task id in snapshot: {task_id}")
        task_ids.add(task_id)
        payload = raw.get("payload", {})
        if not isinstance(payload, Mapping):
            raise ValueError(f"task payload must be a mapping: {task_id}")
        max_attempts = int(raw.get("max_attempts", 3))
        attempts = int(raw.get("attempts", 0))
        if max_attempts < 1 or attempts < 0 or attempts > max_attempts:
            raise ValueError(f"invalid attempts for task: {task_id}")
        try:
            state_value = TaskState(str(raw.get("state", TaskState.QUEUED.value)))
        except ValueError as exc:
            raise ValueError(f"invalid task state: {task_id}") from exc
        owner_raw = raw.get("leased_to")
        deadline_raw = raw.get("lease_deadline")
        owner: str | None = None
        deadline: float | None = None
        if state_value is TaskState.LEASED:
            if not owner_raw:
                raise ValueError(f"leased task missing owner: {task_id}")
            owner = str(owner_raw).strip()
            if not owner:
                raise ValueError(f"leased task missing owner: {task_id}")
            if deadline_raw is None:
                raise ValueError(f"leased task missing deadline: {task_id}")
            deadline = float(deadline_raw)
            if not isfinite(deadline):
                raise ValueError(f"leased task has invalid deadline: {task_id}")
            leased[task_id] = owner
        else:
            if owner_raw is not None:
                raise ValueError(f"non-leased task has owner: {task_id}")
            if deadline_raw is not None:
                raise ValueError(f"non-leased task has deadline: {task_id}")

        record = dict(raw)
        record.update(
            {
                "id": task_id,
                "payload": dict(payload),
                "priority": int(raw.get("priority", 100)),
                "max_attempts": max_attempts,
                "attempts": attempts,
                "state": state_value.value,
                "leased_to": owner,
                "lease_deadline": deadline,
                "required_capabilities": sorted({str(item).strip() for item in raw.get("required_capabilities", ()) if str(item).strip()}),
            }
        )
        clean_tasks.append(record)

    clean_workers: list[dict[str, object]] = []
    active_by_worker: dict[str, set[str]] = {}
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
        active_raw = tuple(str(item).strip() for item in raw.get("active", ()))
        if any(not item for item in active_raw):
            raise ValueError(f"worker has empty active task id: {worker_id}")
        active = set(active_raw)
        if len(active) != len(active_raw):
            raise ValueError(f"worker has duplicate active task: {worker_id}")
        if len(active) > capacity:
            raise ValueError(f"worker active set exceeds capacity: {worker_id}")
        for task_id in active:
            if task_id not in leased:
                raise ValueError(f"worker references non-leased task: {task_id}")
            if leased[task_id] != worker_id:
                raise ValueError(f"worker does not own active task: {task_id}")
        counters = {name: _nonnegative_int(raw.get(name, 0), f"worker {name}: {worker_id}") for name in _WORKER_COUNTERS}
        record = dict(raw)
        record.update(
            {
                "id": worker_id,
                "capacity": capacity,
                "active": sorted(active),
                "capabilities": sorted({str(item).strip() for item in raw.get("capabilities", ()) if str(item).strip()}),
                **counters,
            }
        )
        clean_workers.append(record)
        active_by_worker[worker_id] = active

    missing_workers = sorted({owner for owner in leased.values() if owner not in worker_ids})
    if missing_workers:
        raise ValueError(f"leased task references missing worker: {missing_workers[0]}")
    for task_id, owner in leased.items():
        if task_id not in active_by_worker.get(owner, set()):
            raise ValueError(f"leased task missing from worker active set: {task_id}")

    counters = {name: _nonnegative_int(counters_raw.get(name, 0), f"counter {name}") for name in _COUNTERS}
    if counters["submitted"] < len(task_ids):
        raise ValueError("submitted counter below resident task count")

    clean = dict(state)
    clean["version"] = version
    clean["config"] = config
    clean["tasks"] = clean_tasks
    clean["workers"] = clean_workers
    clean["counters"] = counters
    return clean
