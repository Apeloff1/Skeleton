from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .plan_store import InMemoryPlanStore


@dataclass(slots=True)
class SupervisorHealth:
    clocked_in: int
    working: int
    idle: int
    blocked: int
    overtime_workers: int
    queued_items: int
    assigned_items: int
    working_items: int
    checked_at: str


def snapshot_health(store: InMemoryPlanStore) -> SupervisorHealth:
    workers = store.snapshot_workers()
    items = store.snapshot_items()
    return SupervisorHealth(
        clocked_in=sum(w.status != "offline" for w in workers),
        working=sum(w.status == "working" for w in workers),
        idle=sum(w.status == "idle" for w in workers),
        blocked=sum(w.status == "blocked" for w in workers),
        overtime_workers=sum(w.overtime_minutes > 0 for w in workers),
        queued_items=sum(i.status == "queued" for i in items),
        assigned_items=sum(i.status == "assigned" for i in items),
        working_items=sum(i.status == "working" for i in items),
        checked_at=datetime.now(timezone.utc).isoformat(),
    )
