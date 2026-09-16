from __future__ import annotations

from typing import Any

from .models import PlanItem
from .plan_store import InMemoryPlanStore


class PlanReadAPI:
    """Read-only plan surface for Night/Idle workers and studio controllers."""

    def __init__(self, store: InMemoryPlanStore) -> None:
        self.store = store

    def pending_for_team(self, team: str) -> list[dict[str, Any]]:
        if team not in {"night", "idle"}:
            raise ValueError("team must be night or idle")
        items = [
            item
            for item in self.store.snapshot_items()
            if item.target_team == team and item.status in {"queued", "assigned", "working", "blocked"}
        ]
        items.sort(key=lambda item: (-item.priority, item.created_at))
        return [self._payload(item) for item in items]

    @staticmethod
    def _payload(item: PlanItem) -> dict[str, Any]:
        context_refs = item.metadata.get("context_refs", [])
        conflict_domains = item.metadata.get("conflict_domains", [])
        return {
            "id": item.id,
            "title": item.title,
            "description": item.description,
            "priority": item.priority,
            "status": item.status,
            "owner": item.owner,
            "dependencies": list(item.dependencies),
            "research_refs": list(item.research_refs),
            "context_refs": list(context_refs) if isinstance(context_refs, list) else [],
            "conflict_domains": list(conflict_domains) if isinstance(conflict_domains, list) else [],
            "expected_output": item.expected_output,
            "validation": list(item.validation),
        }


class PlanQueueAPI:
    """Bounded worker-facing queue for pulling orders from the canonical plan.

    Workers never ask the Shift Manager or Secretary for a task. They claim the
    next eligible order from this queue. Claiming is atomic in the store and a
    worker can hold at most one active task, preventing supervisor fan-in and
    per-worker overload. Conflict domains are enforced by the store so workers
    receive parallel work only when active tasks are semantically independent.
    """

    def __init__(self, store: InMemoryPlanStore, *, overtime_soft_limit_minutes: int = 120) -> None:
        self.store = store
        self.overtime_soft_limit_minutes = overtime_soft_limit_minutes

    def claim_next(self, worker_id: str) -> dict[str, Any] | None:
        item = self.store.claim_next_for_worker(
            worker_id,
            overtime_soft_limit_minutes=self.overtime_soft_limit_minutes,
        )
        return PlanReadAPI._payload(item) if item is not None else None

    def complete(self, worker_id: str, item_id: str) -> dict[str, Any]:
        return PlanReadAPI._payload(self.store.finish_claim(worker_id, item_id, outcome="done"))

    def reject(self, worker_id: str, item_id: str) -> dict[str, Any]:
        return PlanReadAPI._payload(self.store.finish_claim(worker_id, item_id, outcome="rejected"))

    def release(self, worker_id: str, item_id: str) -> dict[str, Any]:
        """Return unfinished work to the shared queue without involving a supervisor."""
        return PlanReadAPI._payload(self.store.finish_claim(worker_id, item_id, outcome="queued"))
