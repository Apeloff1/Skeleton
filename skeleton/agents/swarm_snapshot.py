"""Validation and forward-compatible migration helpers for swarm snapshots."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


CURRENT_VERSION = 1


class SnapshotError(ValueError):
    pass


def validate_snapshot(state: Mapping[str, object]) -> None:
    version = state.get("version")
    if version != CURRENT_VERSION:
        raise SnapshotError(f"unsupported snapshot version: {version}")
    config = state.get("config")
    tasks = state.get("tasks")
    workers = state.get("workers")
    counters = state.get("counters")
    if not isinstance(config, Mapping):
        raise SnapshotError("snapshot config must be a mapping")
    if not isinstance(tasks, list):
        raise SnapshotError("snapshot tasks must be a list")
    if not isinstance(workers, list):
        raise SnapshotError("snapshot workers must be a list")
    if not isinstance(counters, Mapping):
        raise SnapshotError("snapshot counters must be a mapping")
    ids: set[str] = set()
    for task in tasks:
        if not isinstance(task, Mapping) or "id" not in task:
            raise SnapshotError("invalid task record")
        task_id = str(task["id"])
        if not task_id or task_id in ids:
            raise SnapshotError(f"invalid or duplicate task id: {task_id}")
        ids.add(task_id)


def normalize_snapshot(state: Mapping[str, object]) -> dict[str, Any]:
    """Return a detached validated snapshot with deterministic collection order."""
    validate_snapshot(state)
    result = deepcopy(dict(state))
    result["tasks"] = sorted(result["tasks"], key=lambda item: str(item["id"]))
    result["workers"] = sorted(result["workers"], key=lambda item: str(item.get("id", "")))
    result["counters"] = dict(sorted(result["counters"].items()))
    return result
