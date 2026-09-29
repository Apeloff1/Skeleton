from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

TeamName = Literal["night", "idle"]
WorkerStatus = Literal["offline", "idle", "working", "blocked"]
PlanStatus = Literal["queued", "assigned", "working", "blocked", "done", "rejected"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class WorkerState:
    worker_id: str
    team: TeamName
    status: WorkerStatus = "offline"
    clocked_in_at: datetime | None = None
    clocked_out_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    current_task_id: str | None = None
    normal_shift_minutes: int = 0
    overtime_minutes: int = 0
    overtime_task_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PlanItem:
    id: str
    title: str
    description: str
    priority: int
    target_team: TeamName
    status: PlanStatus = "queued"
    owner: str | None = None
    dependencies: list[str] = field(default_factory=list)
    source: str = "unknown"
    rationale: str = ""
    research_refs: list[str] = field(default_factory=list)
    expected_output: str = ""
    validation: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PlanRevision:
    revision_id: str
    actor: str
    created_at: datetime
    added_item_ids: list[str] = field(default_factory=list)
    updated_item_ids: list[str] = field(default_factory=list)
    summary: str = ""
    correlation_id: str = ""
