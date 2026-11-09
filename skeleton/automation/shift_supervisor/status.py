from __future__ import annotations

from typing import Any

from .health import snapshot_health
from .plan_store import InMemoryPlanStore


def status_payload(store: InMemoryPlanStore) -> dict[str, Any]:
    health = snapshot_health(store)
    return {
        "clocked_in": health.clocked_in,
        "working": health.working,
        "idle": health.idle,
        "blocked": health.blocked,
        "overtime_workers": health.overtime_workers,
        "queued_items": health.queued_items,
        "assigned_items": health.assigned_items,
        "working_items": health.working_items,
        "checked_at": health.checked_at,
    }
