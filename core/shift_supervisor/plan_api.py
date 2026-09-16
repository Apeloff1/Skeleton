from __future__ import annotations

from typing import Any

from .plan_store import InMemoryPlanStore


class PlanReadAPI:
    """Read-only plan surface for Night/Idle workers."""

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
        return [
            {
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
            }
            for item in items
        ]
