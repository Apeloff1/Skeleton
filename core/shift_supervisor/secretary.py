from __future__ import annotations

import json
import uuid
from typing import Any

from .epistemic_gate import EpistemicExecutionGate
from .model_gateway import ModelGateway
from .models import PlanItem, PlanRevision, utcnow
from .plan_graph import require_acyclic_new_items
from .plan_store import InMemoryPlanStore
from .planning_council import PlanningCouncil
from .prompts import compose_role_prompt
from .task_admission import SECRETARY_PROFILE, admit_model_task, admit_model_tasks


class SecretaryBot:
    """15-minute workload enrichment agent.

    The Secretary expands the canonical plan but never dispatches individual
    workers. Four-agent squads consume accepted tasks through the bounded queue.
    """

    SYSTEM_PROMPT = compose_role_prompt(
        "secretary",
        """Return JSON only with keys summary and tasks. Each proposed task must contain task_key, title, description, priority (1-100), target_team (night|idle), task_type, rationale, research_refs, expected_output, acceptance_criteria, validation, dependencies, conflict_domain, relevant_paths, security_considerations, and performance_considerations. Add only concrete useful workload omitted by the supplied open work. Dependencies must reference another task_key in this response or an exact existing canonical task id and must form an acyclic graph. Do not assign individual workers or emit worker IDs. Every accepted task will use one four-agent squad: researcher, lead, reviewer, verifier. Prefer missing tests, integration, validation, research, documentation, reliability, security, performance evidence, and unblockers. Treat model output as a proposal, never authority.""",
    )

    def __init__(
        self,
        *,
        store: InMemoryPlanStore,
        model: ModelGateway,
        council: PlanningCouncil | None = None,
        gate: EpistemicExecutionGate | None = None,
    ) -> None:
        self.store = store
        self.model = model
        self.council = council
        self.gate = gate

    def enrich_plan(self, project_context: dict[str, Any]) -> PlanRevision:
        correlation_id = f"secretary-{uuid.uuid4()}"
        open_items = [item for item in self.store.snapshot_items() if item.status not in {"done", "rejected"}]
        existing = [
            {
                "id": item.id,
                "task_key": item.metadata.get("task_key"),
                "title": item.title,
                "description": item.description,
                "target_team": item.target_team,
                "status": item.status,
                "conflict_domain": item.metadata.get("conflict_domain"),
            }
            for item in open_items
        ]
        response = self.model.call_json(
            system_prompt=self.SYSTEM_PROMPT,
            user_prompt=json.dumps({"project_context": project_context, "open_work": existing}, default=str),
            correlation_id=correlation_id,
        )
        raw_proposals = response.get("tasks", [])
        proposals = (
            [dict(task) for task in raw_proposals if isinstance(task, dict)]
            if isinstance(raw_proposals, list)
            else []
        )
        if self.council is not None:
            proposals = self.council.review_tasks(
                proposals,
                context={"project_context": project_context, "open_work": existing},
                correlation_id=correlation_id,
                actor="secretary",
            )
        if self.gate is not None:
            proposals = self.gate.filter_tasks(proposals)
        items = self._parse_tasks(
            proposals,
            correlation_id,
            existing_ids={item.id for item in open_items},
        )
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
    def _parse_tasks(
        cls,
        tasks: list[dict[str, Any]],
        correlation_id: str,
        *,
        existing_ids: set[str],
    ) -> list[PlanItem]:
        """Compatibility wrapper over the shared planning admission contract."""
        return admit_model_tasks(
            tasks,
            correlation_id,
            existing_ids=existing_ids,
            profile=SECRETARY_PROFILE,
        )

    @staticmethod
    def _parse_task(
        task: dict[str, Any],
        correlation_id: str,
        *,
        item_id: str | None = None,
        task_key: str | None = None,
        dependencies: list[str] | None = None,
    ) -> PlanItem | None:
        """Compatibility wrapper for focused tests and legacy callers."""
        resolved_key = (
            str(task_key).strip()
            if task_key is not None
            else str(task.get("task_key", "")).strip() or "proposal-1"
        )
        raw_dependencies = task.get("dependencies", [])
        resolved_dependencies = (
            list(dependencies)
            if dependencies is not None
            else [str(value) for value in raw_dependencies if value]
            if isinstance(raw_dependencies, list)
            else []
        )
        return admit_model_task(
            task,
            correlation_id,
            profile=SECRETARY_PROFILE,
            item_id=item_id or f"sec-{uuid.uuid4()}",
            task_key=resolved_key,
            dependencies=resolved_dependencies,
        )
