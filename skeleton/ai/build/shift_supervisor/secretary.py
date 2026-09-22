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
from .squads import SQUAD_ROLES, SQUAD_SIZE


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
        staged: list[tuple[dict[str, Any], str, str]] = []
        key_to_id: dict[str, str] = {}
        for index, task in enumerate(tasks[:128]):
            title = str(task.get("title", "")).strip()
            description = str(task.get("description", "")).strip()
            team = str(task.get("target_team", "")).strip().lower()
            if not title or not description or team not in {"night", "idle"}:
                continue
            task_key = str(task.get("task_key", "")).strip() or f"proposal-{index + 1}"
            if task_key in key_to_id:
                return []
            item_id = f"sec-{uuid.uuid4()}"
            key_to_id[task_key] = item_id
            staged.append((task, task_key, item_id))

        resolved_dependencies: dict[str, list[str]] = {}
        for task, _task_key, item_id in staged:
            raw_dependencies = task.get("dependencies", [])
            if not isinstance(raw_dependencies, list):
                return []
            dependency_names = [str(value).strip() for value in raw_dependencies if str(value).strip()]
            if any(name not in key_to_id and name not in existing_ids for name in dependency_names):
                return []
            resolved_dependencies[item_id] = [key_to_id.get(name, name) for name in dependency_names]

        result: list[PlanItem] = []
        for task, task_key, item_id in staged:
            item = cls._parse_task(
                task,
                correlation_id,
                item_id=item_id,
                task_key=task_key,
                dependencies=resolved_dependencies[item_id],
            )
            if item is None:
                return []
            result.append(item)
        return require_acyclic_new_items(result)

    @staticmethod
    def _parse_task(
        task: dict[str, Any],
        correlation_id: str,
        *,
        item_id: str | None = None,
        task_key: str | None = None,
        dependencies: list[str] | None = None,
    ) -> PlanItem | None:
        title = str(task.get("title", "")).strip()
        description = str(task.get("description", "")).strip()
        team = str(task.get("target_team", "")).strip().lower()
        if not title or not description or team not in {"night", "idle"}:
            return None
        try:
            priority = max(1, min(100, int(task.get("priority", 50))))
        except (TypeError, ValueError):
            priority = 50
        paths = [str(value)[:500] for value in task.get("relevant_paths", [])[:32]] if isinstance(task.get("relevant_paths"), list) else []
        conflict_domain = str(task.get("conflict_domain", "")).strip()
        if not conflict_domain and paths:
            conflict_domain = "/".join(paths[0].strip("/").split("/")[:2])
        conflict_domain = conflict_domain or f"task:{task_key or title}"
        acceptance = [str(value)[:1000] for value in task.get("acceptance_criteria", [])[:32]] if isinstance(task.get("acceptance_criteria"), list) else []
        metadata: dict[str, Any] = {
            "correlation_id": correlation_id,
            "task_key": task_key or str(task.get("task_key", "")).strip(),
            "task_type": str(task.get("task_type", "engineering"))[:100],
            "squad_size": SQUAD_SIZE,
            "squad_roles": list(SQUAD_ROLES),
            "conflict_domain": conflict_domain[:300],
            "relevant_paths": paths,
            "acceptance_criteria": acceptance,
            "security_considerations": str(task.get("security_considerations", ""))[:2000],
            "performance_considerations": str(task.get("performance_considerations", ""))[:2000],
        }
        council = task.get("_planning_council")
        if isinstance(council, dict):
            metadata["planning_council"] = dict(council)
        gate = task.get("_epistemic_gate")
        if isinstance(gate, dict):
            metadata["epistemic_gate"] = dict(gate)
        return PlanItem(
            id=item_id or f"sec-{uuid.uuid4()}",
            title=title,
            description=description,
            priority=priority,
            target_team=team,  # type: ignore[arg-type]
            dependencies=dependencies if dependencies is not None else [str(x) for x in task.get("dependencies", []) if x],
            source="secretary-model",
            rationale=str(task.get("rationale", "")),
            research_refs=[str(x) for x in task.get("research_refs", []) if x],
            expected_output=str(task.get("expected_output", "")),
            validation=[str(x) for x in task.get("validation", []) if x],
            metadata=metadata,
        )