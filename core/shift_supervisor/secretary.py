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

    SYSTEM_PROMPT = """You are the Secretary for two autonomous software-work teams: night and idle.\nReturn JSON only with keys summary and tasks. Each task must contain title, description, priority (1-100), target_team (night|idle), rationale, research_refs, expected_output, validation, dependencies. Add only concrete, useful workload that advances the supplied project state. Do not duplicate supplied open work. Do not assign tasks to individual workers and do not emit worker IDs; workers pull eligible orders from the shared canonical plan. Prefer missing tests, integration work, validation, research, documentation, reliability, security, and unblockers. Treat model output as a proposal, not authority."""

    def __init__(self, *, store: InMemoryPlanStore, model: ModelGateway) -> None:
        self.store = store
        self.model = model

    def enrich_plan(self, project_context: dict[str, Any]) -> PlanRevision:
        correlation_id = f"secretary-{uuid.uuid4()}"
        existing_items = self.store.snapshot_items()
        existing = [
            {
                "id": item.id,
                "title": item.title,
                "description": item.description,
                "target_team": item.target_team,
                "status": item.status,
            }
            for item in existing_items
            if item.status not in {"done", "rejected"}
        ]
        response = self.model.call_json(
            system_prompt=self.SYSTEM_PROMPT,
            user_prompt=json.dumps(
                {
                    "project_context": self._planning_context(project_context),
                    "open_work": existing,
                },
                default=str,
            ),
            correlation_id=correlation_id,
        )
        proposals = response.get("tasks", [])
        parsed = [self._parse_task(task, correlation_id) for task in proposals if isinstance(task, dict)]
        parsed_items = [item for item in parsed if item is not None]
        dependency_ids = {item.id for item in existing_items if item.status != "rejected"}
        accepted_items = [
            item for item in parsed_items if self._dependencies_resolvable(item, dependency_ids)
        ]
        rejected_dependencies = len(parsed_items) - len(accepted_items)
        added = self.store.add_items(accepted_items)
        summary = str(response.get("summary", ""))
        if rejected_dependencies:
            summary = (
                f"{summary.rstrip()} Skipped {rejected_dependencies} task(s) with unresolved dependencies."
            ).strip()
        revision = PlanRevision(
            revision_id=f"rev-{uuid.uuid4()}",
            actor="secretary",
            created_at=utcnow(),
            added_item_ids=added,
            summary=summary,
            correlation_id=correlation_id,
        )
        self.store.append_revision(revision)
        return revision

    @staticmethod
    def _planning_context(project_context: dict[str, Any]) -> dict[str, Any]:
        """Keep raw workforce records local to orchestration, not the model."""
        context = dict(project_context)
        snapshots = context.pop("worker_snapshots", None)
        if isinstance(snapshots, list):
            context["worker_snapshot_count"] = len(snapshots)
        return context

    @staticmethod
    def _dependencies_resolvable(item: PlanItem, dependency_ids: set[str]) -> bool:
        """Reject model work that can never become queue-eligible."""
        return all(dependency_id in dependency_ids for dependency_id in item.dependencies)

    @staticmethod
    def _parse_task(task: dict[str, Any], correlation_id: str) -> PlanItem | None:
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
            metadata={"correlation_id": correlation_id},
        )
