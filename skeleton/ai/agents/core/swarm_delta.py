"""Compact deterministic deltas between swarm snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class SnapshotDelta:
    added_tasks: tuple[str, ...]
    removed_tasks: tuple[str, ...]
    changed_tasks: tuple[str, ...]
    added_workers: tuple[str, ...]
    removed_workers: tuple[str, ...]


def _index(items: object) -> dict[str, Mapping[str, object]]:
    if not isinstance(items, list):
        return {}
    result: dict[str, Mapping[str, object]] = {}
    for item in items:
        if isinstance(item, Mapping) and "id" in item:
            result[str(item["id"])] = item
    return result


def diff_snapshots(before: Mapping[str, object], after: Mapping[str, object]) -> SnapshotDelta:
    before_tasks = _index(before.get("tasks"))
    after_tasks = _index(after.get("tasks"))
    before_workers = _index(before.get("workers"))
    after_workers = _index(after.get("workers"))

    before_task_ids = set(before_tasks)
    after_task_ids = set(after_tasks)
    common_tasks = before_task_ids & after_task_ids
    changed = sorted(task_id for task_id in common_tasks if before_tasks[task_id] != after_tasks[task_id])

    return SnapshotDelta(
        added_tasks=tuple(sorted(after_task_ids - before_task_ids)),
        removed_tasks=tuple(sorted(before_task_ids - after_task_ids)),
        changed_tasks=tuple(changed),
        added_workers=tuple(sorted(set(after_workers) - set(before_workers))),
        removed_workers=tuple(sorted(set(before_workers) - set(after_workers))),
    )
