from __future__ import annotations

from typing import Any, Mapping, Sequence

from .models import PlanItem
from .plan_store import InMemoryPlanStore
from .squads import SQUAD_SIZE, SquadCoordinator


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
        return {
            "id": item.id,
            "title": item.title,
            "description": item.description,
            "priority": item.priority,
            "status": item.status,
            "owner": item.owner,
            "dependencies": list(item.dependencies),
            "research_refs": list(item.research_refs),
            "expected_output": item.expected_output,
            "validation": list(item.validation),
            "metadata": dict(item.metadata),
        }


class PlanQueueAPI:
    """Legacy single-worker queue for explicitly single-worker plan items.

    Four-agent tasks are released immediately if this legacy API encounters one.
    New autonomous engineering work should use ``SquadPlanQueueAPI`` so a task
    and all four workers are reserved atomically.
    """

    def __init__(self, store: InMemoryPlanStore, *, overtime_soft_limit_minutes: int = 120) -> None:
        self.store = store
        self.overtime_soft_limit_minutes = overtime_soft_limit_minutes

    def claim_next(self, worker_id: str) -> dict[str, Any] | None:
        item = self.store.claim_next_for_worker(
            worker_id,
            overtime_soft_limit_minutes=self.overtime_soft_limit_minutes,
        )
        if item is None:
            return None
        if int(item.metadata.get("squad_size", 1)) == SQUAD_SIZE:
            # Compatibility guard: never let the old one-worker API retain a
            # four-person task. The squad coordinator is the authority for it.
            self.store.finish_claim(worker_id, item.id, outcome="queued")
            return None
        return PlanReadAPI._payload(item)

    def complete(self, worker_id: str, item_id: str) -> dict[str, Any]:
        return PlanReadAPI._payload(self.store.finish_claim(worker_id, item_id, outcome="done"))

    def reject(self, worker_id: str, item_id: str) -> dict[str, Any]:
        return PlanReadAPI._payload(self.store.finish_claim(worker_id, item_id, outcome="rejected"))

    def release(self, worker_id: str, item_id: str) -> dict[str, Any]:
        """Return unfinished single-worker work to the shared queue."""
        return PlanReadAPI._payload(self.store.finish_claim(worker_id, item_id, outcome="queued"))


class SquadPlanQueueAPI:
    """Worker-facing four-agent queue for canonical anti-swarm execution."""

    def __init__(
        self,
        store: InMemoryPlanStore,
        *,
        overtime_soft_limit_minutes: int = 120,
        default_lease_minutes: int = 45,
    ) -> None:
        self.coordinator = SquadCoordinator(
            store,
            overtime_soft_limit_minutes=overtime_soft_limit_minutes,
            default_lease_minutes=default_lease_minutes,
        )

    def safe_capacity(self, team: str) -> int:
        return self.coordinator.safe_capacity(team)

    def claim_next(
        self,
        team: str,
        *,
        plan_generation: str,
        worker_ids: Sequence[str] | None = None,
    ) -> dict[str, Any] | None:
        lease = self.coordinator.claim_next(
            team,
            plan_generation=plan_generation,
            worker_ids=worker_ids,
        )
        return lease.to_dict() if lease is not None else None

    def renew(self, squad_id: str, task_id: str, *, minutes: int | None = None) -> dict[str, Any]:
        return self.coordinator.renew(squad_id, task_id, minutes=minutes).to_dict()

    def complete(
        self,
        squad_id: str,
        task_id: str,
        *,
        evidence: Mapping[str, Any],
    ) -> dict[str, Any]:
        return PlanReadAPI._payload(
            self.coordinator.finish(squad_id, task_id, outcome="done", evidence=evidence)
        )

    def reject(
        self,
        squad_id: str,
        task_id: str,
        *,
        evidence: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return PlanReadAPI._payload(
            self.coordinator.finish(squad_id, task_id, outcome="rejected", evidence=evidence)
        )

    def release(
        self,
        squad_id: str,
        task_id: str,
        *,
        evidence: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return PlanReadAPI._payload(
            self.coordinator.finish(squad_id, task_id, outcome="queued", evidence=evidence)
        )

    def reclaim_expired(self) -> list[str]:
        return self.coordinator.reclaim_expired()
