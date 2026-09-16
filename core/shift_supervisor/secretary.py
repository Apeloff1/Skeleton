from __future__ import annotations

import json
import uuid
from typing import Any

from .model_gateway import ModelGateway
from .models import PlanItem, PlanRevision, utcnow
from .plan_store import InMemoryPlanStore


class SecretaryBot:
    """15-minute workload enrichment agent.

    The Secretary expands the canonical plan but never dispatches individual
    workers. Workers consume the resulting plan through the bounded queue.
    """

    SYSTEM_PROMPT = """You are the Secretary for two autonomous software-work teams: night and idle.\nReturn JSON only with keys summary and tasks. Each task must contain title, description, priority (1-100), target_team (night|idle), rationale, research_refs, context_refs, conflict_domains, expected_output, validation, dependencies. Add only concrete, useful workload that advances the supplied project state. Do not duplicate supplied open work. Use context_refs for the smallest repository/contracts/docs a worker needs instead of copying broad context. Use stable conflict_domains (for example path:core/shift_supervisor, workflow:idle-studio, api:plan-queue) so overlapping work serializes while independent work can run in parallel. Treat recent failure/audit traces as evidence: recurring failures should become a focused harness, regression, observability, or recovery task rather than repeated blind retries. Do not assign tasks to individual workers and do not emit worker IDs; workers pull eligible orders from the shared canonical plan. Prefer missing tests, integration work, validation, research, documentation, reliability, security, and unblockers. Treat model output as a proposal, not authority."""

    def __init__(self, *, store: InMemoryPlanStore, model: ModelGateway) -> None:
        self.store = store
        self.model = model

    def enrich_plan(self, project_context: dict[str, Any]) -> PlanRevision:
        correlation_id = f"secretary-{uuid.uuid4()}"
        existing = [
            {
                "id": item.id,
                "title": item.title,
                "description": item.description,
                "target_team": item.target_team,
                "status": item.status,
                "context_refs": self._metadata_strings(item, "context_refs"),
                "conflict_domains": self._metadata_strings(item, "conflict_domains"),
            }
            for item in self.store.snapshot_items()
            if item.status not in {"done", "rejected"}
        ]
        response = self.model.call_json(
            system_prompt=self.SYSTEM_PROMPT,
            user_prompt=json.dumps({"project_context": project_context, "open_work": existing}, default=str),
            correlation_id=correlation_id,
        )
        proposals = response.get("tasks", [])
        items = [self._parse_task(task, correlation_id) for task in proposals if isinstance(task, dict)]
        items = [item for item in items if item is not None]
        added = self.store.add_items(items)
        revision = PlanRevision(
            revision_id=f"rev-{uuid.uuid4()}",
            actor="secretary",
            created_at=utcnow(),
            added_item_ids=added,
            summary=str(response.get("summary", "")),
            correlation_id=correlation_id,
        )
        self.store.append_revision(revision)
        return revision

    @classmethod
    def _parse_task(cls, task: dict[str, Any], correlation_id: str) -> PlanItem | None:
        title = str(task.get("title", "")).strip()
        description = str(task.get("description", "")).strip()
        team = str(task.get("target_team", "")).strip().lower()
        if not title or not description or team not in {"night", "idle"}:
            return None
        try:
            priority = max(1, min(100, int(task.get("priority", 50))))
        except (TypeError, ValueError):
            priority = 50
        return PlanItem(
            id=f"sec-{uuid.uuid4()}",
            title=title,
            description=description,
            priority=priority,
            target_team=team,  # type: ignore[arg-type]
            dependencies=[str(x) for x in task.get("dependencies", []) if x],
            source="secretary-model",
            rationale=str(task.get("rationale", "")),
            research_refs=[str(x) for x in task.get("research_refs", []) if x],
            expected_output=str(task.get("expected_output", "")),
            validation=[str(x) for x in task.get("validation", []) if x],
            metadata={
                "correlation_id": correlation_id,
                "context_refs": cls._bounded_strings(task.get("context_refs"), 24),
                "conflict_domains": cls._bounded_strings(task.get("conflict_domains"), 16),
            },
        )

    @staticmethod
    def _bounded_strings(value: Any, limit: int) -> list[str]:
        if not isinstance(value, list):
            return []
        result: list[str] = []
        for raw in value:
            text = str(raw).strip()
            if text and text not in result:
                result.append(text[:256])
            if len(result) >= limit:
                break
        return result

    @staticmethod
    def _metadata_strings(item: PlanItem, key: str) -> list[str]:
        value = item.metadata.get(key, [])
        if not isinstance(value, list):
            return []
        return [str(entry) for entry in value[:24] if str(entry).strip()]
