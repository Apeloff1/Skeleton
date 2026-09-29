from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from .models import PlanItem


def require_acyclic_new_items(items: Iterable[PlanItem]) -> list[PlanItem]:
    """Return items when their new-item dependency graph is acyclic.

    Dependencies pointing to canonical items outside this batch are treated as
    already-existing graph edges and do not participate in this local cycle
    check. Any cycle among newly proposed tasks rejects the whole batch so the
    planner cannot leave permanently blocked partial work behind.
    """
    result = list(items)
    by_id = {item.id: item for item in result}
    if len(by_id) != len(result):
        raise ValueError("duplicate canonical task IDs in plan batch")

    indegree = {item_id: 0 for item_id in by_id}
    dependents: dict[str, list[str]] = {item_id: [] for item_id in by_id}
    for item in result:
        for dependency in item.dependencies:
            if dependency not in by_id:
                continue
            indegree[item.id] += 1
            dependents[dependency].append(item.id)

    ready = deque(sorted(item_id for item_id, degree in indegree.items() if degree == 0))
    visited = 0
    while ready:
        item_id = ready.popleft()
        visited += 1
        for dependent in sorted(dependents[item_id]):
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                ready.append(dependent)

    if visited != len(result):
        cyclic = sorted(item_id for item_id, degree in indegree.items() if degree > 0)
        raise ValueError(f"cyclic plan dependencies rejected: {cyclic!r}")
    return result
