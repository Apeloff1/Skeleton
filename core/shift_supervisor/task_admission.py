from __future__ import annotations

"""Shared fail-closed admission for Supervisor/Secretary model task proposals.

Planning actors are proposal producers, not dispatch authorities.  This module
owns the conversion from untrusted model-shaped task dictionaries into the
canonical PlanItem schema consumed by the four-agent worker queue.

The Manager and Secretary intentionally share this implementation so dependency
resolution, squad stamping, conflict domains, and evidence metadata cannot drift
between the 15-minute and 30-minute planning paths.
"""

import uuid
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .models import PlanItem
from .plan_graph import require_acyclic_new_items
from .squads import SQUAD_ROLES, SQUAD_SIZE

MAX_PROPOSALS = 128
MAX_TASK_KEY = 240
MAX_TITLE = 500
MAX_DESCRIPTION = 8_000
MAX_LIST_ITEMS = 32
MAX_LIST_TEXT = 1_000
MAX_PATH = 500
MAX_CONFLICT_DOMAIN = 300
MAX_TASK_TYPE = 100
MAX_CONSIDERATION = 2_000


@dataclass(frozen=True, slots=True)
class TaskAdmissionProfile:
    """Actor-specific identity while preserving one canonical task contract."""

    id_prefix: str
    source: str

    def __post_init__(self) -> None:
        if not isinstance(self.id_prefix, str) or not self.id_prefix.strip():
            raise ValueError("id_prefix is required")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("source is required")
        if "\x00" in self.id_prefix or "\x00" in self.source:
            raise ValueError("admission profile contains NUL")


MANAGER_PROFILE = TaskAdmissionProfile("mgr", "shift-manager-model")
SECRETARY_PROFILE = TaskAdmissionProfile("sec", "secretary-model")


def _text(value: Any, *, limit: int, default: str = "") -> str:
    """Bound model text while retaining historical string-coercion semantics."""

    if value is None:
        return default
    text = str(value).strip()
    if "\x00" in text:
        return default
    return text[:limit]


def _string_list(
    value: Any,
    *,
    limit: int = MAX_LIST_ITEMS,
    chars: int = MAX_LIST_TEXT,
) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for raw in value[:limit]:
        text = _text(raw, limit=chars)
        if text:
            result.append(text)
    return result


def _priority(value: Any) -> int:
    """Preserve legacy default/clamp behavior while refusing bool coercion."""

    if isinstance(value, bool):
        return 50
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return 50
    return max(1, min(100, parsed))


def _task_key(task: Mapping[str, Any], index: int) -> str:
    key = _text(task.get("task_key"), limit=MAX_TASK_KEY)
    return key or f"proposal-{index + 1}"


def _relevant_paths(task: Mapping[str, Any]) -> list[str]:
    return _string_list(task.get("relevant_paths"), chars=MAX_PATH)


def _conflict_domain(
    task: Mapping[str, Any],
    *,
    relevant_paths: Sequence[str],
    task_key: str,
    title: str,
) -> str:
    explicit = _text(task.get("conflict_domain"), limit=MAX_CONFLICT_DOMAIN)
    if explicit:
        return explicit
    if relevant_paths:
        path = relevant_paths[0].strip("/")
        inferred = "/".join(path.split("/")[:2]).strip()
        if inferred:
            return inferred[:MAX_CONFLICT_DOMAIN]
    return f"task:{task_key or title}"[:MAX_CONFLICT_DOMAIN]


def _annotation(task: Mapping[str, Any], key: str) -> dict[str, Any] | None:
    value = task.get(key)
    return dict(value) if isinstance(value, Mapping) else None


def admit_model_task(
    task: Mapping[str, Any],
    correlation_id: str,
    *,
    profile: TaskAdmissionProfile,
    item_id: str,
    task_key: str,
    dependencies: list[str],
) -> PlanItem | None:
    """Convert one already dependency-resolved proposal to a canonical item."""

    title = _text(task.get("title"), limit=MAX_TITLE)
    description = _text(task.get("description"), limit=MAX_DESCRIPTION)
    team = _text(task.get("target_team"), limit=16).lower()
    if not title or not description or team not in {"night", "idle"}:
        return None

    paths = _relevant_paths(task)
    conflict_domain = _conflict_domain(
        task,
        relevant_paths=paths,
        task_key=task_key,
        title=title,
    )
    acceptance = _string_list(task.get("acceptance_criteria"))
    validation = _string_list(task.get("validation"))
    research_refs = _string_list(task.get("research_refs"))
    metadata: dict[str, Any] = {
        "correlation_id": _text(correlation_id, limit=500),
        "task_key": task_key,
        "task_type": _text(
            task.get("task_type"),
            limit=MAX_TASK_TYPE,
            default="engineering",
        )
        or "engineering",
        "squad_size": SQUAD_SIZE,
        "squad_roles": list(SQUAD_ROLES),
        "conflict_domain": conflict_domain,
        "relevant_paths": paths,
        "acceptance_criteria": acceptance,
        "security_considerations": _text(
            task.get("security_considerations"),
            limit=MAX_CONSIDERATION,
        ),
        "performance_considerations": _text(
            task.get("performance_considerations"),
            limit=MAX_CONSIDERATION,
        ),
    }
    council = _annotation(task, "_planning_council")
    if council is not None:
        metadata["planning_council"] = council
    gate = _annotation(task, "_epistemic_gate")
    if gate is not None:
        metadata["epistemic_gate"] = gate

    return PlanItem(
        id=item_id,
        title=title,
        description=description,
        priority=_priority(task.get("priority", 50)),
        target_team=team,  # type: ignore[arg-type]
        dependencies=list(dependencies),
        source=profile.source,
        rationale=_text(task.get("rationale"), limit=MAX_DESCRIPTION),
        research_refs=research_refs,
        expected_output=_text(task.get("expected_output"), limit=MAX_DESCRIPTION),
        validation=validation,
        metadata=metadata,
    )


def admit_model_tasks(
    tasks: Sequence[Mapping[str, Any]],
    correlation_id: str,
    *,
    existing_ids: set[str],
    profile: TaskAdmissionProfile,
) -> list[PlanItem]:
    """Admit one bounded proposal batch.

    Invalid title/team rows retain the historical behavior of being omitted.
    Structural ambiguity is different: duplicate task keys, malformed dependency
    collections, unresolved dependencies, invalid fully-staged rows, and cycles
    reject the entire batch.  That prevents partial dependency graphs from
    becoming executable canonical work.
    """

    if isinstance(tasks, (str, bytes)):
        return []
    staged: list[tuple[Mapping[str, Any], str, str]] = []
    key_to_id: dict[str, str] = {}

    for index, raw in enumerate(tuple(tasks)[:MAX_PROPOSALS]):
        if not isinstance(raw, Mapping):
            return []
        title = _text(raw.get("title"), limit=MAX_TITLE)
        description = _text(raw.get("description"), limit=MAX_DESCRIPTION)
        team = _text(raw.get("target_team"), limit=16).lower()
        if not title or not description or team not in {"night", "idle"}:
            continue

        task_key = _task_key(raw, index)
        if task_key in key_to_id:
            return []
        item_id = f"{profile.id_prefix}-{uuid.uuid4()}"
        key_to_id[task_key] = item_id
        staged.append((raw, task_key, item_id))

    resolved_dependencies: dict[str, list[str]] = {}
    for task, _task_key_value, item_id in staged:
        raw_dependencies = task.get("dependencies", [])
        if not isinstance(raw_dependencies, list):
            return []
        dependency_names: list[str] = []
        for raw_dependency in raw_dependencies[:MAX_LIST_ITEMS]:
            dependency = _text(raw_dependency, limit=500)
            if not dependency:
                continue
            dependency_names.append(dependency)
        if len(set(dependency_names)) != len(dependency_names):
            return []
        if any(
            dependency not in key_to_id and dependency not in existing_ids
            for dependency in dependency_names
        ):
            return []
        resolved_dependencies[item_id] = [
            key_to_id.get(dependency, dependency)
            for dependency in dependency_names
        ]

    parsed: list[PlanItem] = []
    for task, task_key, item_id in staged:
        item = admit_model_task(
            task,
            correlation_id,
            profile=profile,
            item_id=item_id,
            task_key=task_key,
            dependencies=resolved_dependencies[item_id],
        )
        if item is None:
            return []
        parsed.append(item)

    return require_acyclic_new_items(parsed)
