"""Deterministic P3 workflow IR, compiler, critical path and scheduler.

This module is intentionally stdlib-only and execution-neutral.  It compiles a
bounded declarative workflow into a canonical immutable IR, proves dependency
soundness, calculates the weighted critical path, and simulates deterministic
conflict-aware scheduling.  It grants no tool or mutation authority by itself.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Iterable, Mapping, Sequence


_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_ALLOWED_KINDS = frozenset(
    {
        "generic",
        "research",
        "analysis",
        "code",
        "test",
        "review",
        "verify",
        "build",
        "deploy",
        "recovery",
    }
)
_ALLOWED_EFFECTS = frozenset({"pure", "read", "write", "external"})


class WorkflowCompileError(RuntimeError):
    """Workflow source is unsafe, ambiguous, cyclic, or outside bounds."""


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise WorkflowCompileError("workflow source must be deterministic JSON") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _identifier(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise WorkflowCompileError(f"{field} must be text")
    text = value.strip()
    if not _ID.fullmatch(text):
        raise WorkflowCompileError(f"{field} is not a canonical bounded identifier")
    return text


def _bounded_text(value: object, field: str, *, maximum: int = 4096) -> str:
    if not isinstance(value, str):
        raise WorkflowCompileError(f"{field} must be text")
    text = value.strip()
    if not text or len(text) > maximum:
        raise WorkflowCompileError(f"{field} must be non-empty and <= {maximum} chars")
    return text


def _id_list(value: object, field: str, *, maximum: int = 128) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise WorkflowCompileError(f"{field} must be a list")
    if len(value) > maximum:
        raise WorkflowCompileError(f"{field} exceeds maximum item count")
    normalized = tuple(_identifier(item, field) for item in value)
    if len(normalized) != len(set(normalized)):
        raise WorkflowCompileError(f"{field} must be unique")
    return tuple(sorted(normalized))


@dataclass(frozen=True, slots=True)
class WorkflowTask:
    task_id: str
    kind: str
    objective: str
    depends_on: tuple[str, ...]
    conflict_keys: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    estimated_effort: int
    max_attempts: int
    effect_class: str
    approval_required: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _identifier(self.task_id, "task_id"))
        if self.kind not in _ALLOWED_KINDS:
            raise WorkflowCompileError(f"{self.task_id} unsupported task kind {self.kind!r}")
        object.__setattr__(
            self,
            "objective",
            _bounded_text(self.objective, f"{self.task_id}.objective"),
        )
        for field in ("depends_on", "conflict_keys", "required_capabilities"):
            value = tuple(getattr(self, field))
            if len(value) != len(set(value)):
                raise WorkflowCompileError(f"{self.task_id}.{field} contains duplicates")
            for item in value:
                _identifier(item, f"{self.task_id}.{field}")
            object.__setattr__(self, field, tuple(sorted(value)))
        if self.task_id in self.depends_on:
            raise WorkflowCompileError(f"{self.task_id} cannot depend on itself")
        if (
            isinstance(self.estimated_effort, bool)
            or not isinstance(self.estimated_effort, int)
            or not 1 <= self.estimated_effort <= 10_000
        ):
            raise WorkflowCompileError(
                f"{self.task_id}.estimated_effort must be integer in [1,10000]"
            )
        if (
            isinstance(self.max_attempts, bool)
            or not isinstance(self.max_attempts, int)
            or not 1 <= self.max_attempts <= 32
        ):
            raise WorkflowCompileError(
                f"{self.task_id}.max_attempts must be integer in [1,32]"
            )
        if self.effect_class not in _ALLOWED_EFFECTS:
            raise WorkflowCompileError(
                f"{self.task_id} unsupported effect_class {self.effect_class!r}"
            )
        if not isinstance(self.approval_required, bool):
            raise WorkflowCompileError(
                f"{self.task_id}.approval_required must be boolean"
            )
        if self.effect_class in {"write", "external"} and not self.approval_required:
            raise WorkflowCompileError(
                f"{self.task_id} effectful task requires explicit approval"
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "kind": self.kind,
            "objective": self.objective,
            "depends_on": list(self.depends_on),
            "conflict_keys": list(self.conflict_keys),
            "required_capabilities": list(self.required_capabilities),
            "estimated_effort": self.estimated_effort,
            "max_attempts": self.max_attempts,
            "effect_class": self.effect_class,
            "approval_required": self.approval_required,
        }


@dataclass(frozen=True, slots=True)
class CompiledWorkflow:
    workflow_id: str
    version: str
    source_digest: str
    ir_digest: str
    tasks: tuple[WorkflowTask, ...]
    topological_order: tuple[str, ...]

    def __post_init__(self) -> None:
        _identifier(self.workflow_id, "workflow_id")
        _identifier(self.version, "version")
        for field in ("source_digest", "ir_digest"):
            value = getattr(self, field)
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(ch not in "0123456789abcdef" for ch in value)
            ):
                raise WorkflowCompileError(f"{field} must be lowercase sha256")
        ids = tuple(task.task_id for task in self.tasks)
        if len(ids) != len(set(ids)):
            raise WorkflowCompileError("compiled task ids must be unique")
        if set(self.topological_order) != set(ids) or len(self.topological_order) != len(ids):
            raise WorkflowCompileError("topological order must cover tasks exactly")

    @property
    def task_map(self) -> dict[str, WorkflowTask]:
        return {task.task_id: task for task in self.tasks}

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.workflow_ir.v1",
            "workflow_id": self.workflow_id,
            "version": self.version,
            "source_digest": self.source_digest,
            "ir_digest": self.ir_digest,
            "tasks": [task.as_dict() for task in self.tasks],
            "topological_order": list(self.topological_order),
        }


def _topological(tasks: Sequence[WorkflowTask]) -> tuple[str, ...]:
    by_id = {task.task_id: task for task in tasks}
    indegree = {task_id: 0 for task_id in by_id}
    dependents: dict[str, set[str]] = {task_id: set() for task_id in by_id}
    for task in tasks:
        for dep in task.depends_on:
            if dep not in by_id:
                raise WorkflowCompileError(
                    f"{task.task_id} depends on unknown task {dep}"
                )
            indegree[task.task_id] += 1
            dependents[dep].add(task.task_id)

    ready = sorted(task_id for task_id, degree in indegree.items() if degree == 0)
    order: list[str] = []
    while ready:
        task_id = ready.pop(0)
        order.append(task_id)
        for child in sorted(dependents[task_id]):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
                ready.sort()
    if len(order) != len(tasks):
        remaining = sorted(task_id for task_id, degree in indegree.items() if degree)
        raise WorkflowCompileError(
            "workflow dependency cycle: " + ",".join(remaining)
        )
    return tuple(order)


class WorkflowCompiler:
    """Compile a bounded JSON-shaped workflow source into canonical IR."""

    def __init__(self, *, max_tasks: int = 512) -> None:
        if (
            isinstance(max_tasks, bool)
            or not isinstance(max_tasks, int)
            or not 1 <= max_tasks <= 4096
        ):
            raise ValueError("max_tasks must be integer in [1,4096]")
        self.max_tasks = max_tasks

    def compile(self, source: Mapping[str, Any]) -> CompiledWorkflow:
        if not isinstance(source, Mapping):
            raise WorkflowCompileError("workflow source must be a mapping")
        canonical_source = json.loads(_canonical_json(dict(source)))
        workflow_id = _identifier(canonical_source.get("workflow_id"), "workflow_id")
        version = _identifier(canonical_source.get("version"), "version")
        rows = canonical_source.get("tasks")
        if not isinstance(rows, list) or not rows:
            raise WorkflowCompileError("workflow requires a non-empty tasks list")
        if len(rows) > self.max_tasks:
            raise WorkflowCompileError("workflow exceeds max_tasks")

        tasks: list[WorkflowTask] = []
        seen: set[str] = set()
        for index, row in enumerate(rows):
            if not isinstance(row, Mapping):
                raise WorkflowCompileError(f"tasks[{index}] must be an object")
            task_id = _identifier(row.get("task_id"), f"tasks[{index}].task_id")
            if task_id in seen:
                raise WorkflowCompileError(f"duplicate task_id: {task_id}")
            seen.add(task_id)
            kind = str(row.get("kind", "generic")).strip().lower()
            effect = str(row.get("effect_class", "pure")).strip().lower()
            estimated = row.get("estimated_effort", 1)
            attempts = row.get("max_attempts", 1)
            approval = row.get("approval_required", False)
            tasks.append(
                WorkflowTask(
                    task_id=task_id,
                    kind=kind,
                    objective=_bounded_text(
                        row.get("objective"),
                        f"{task_id}.objective",
                    ),
                    depends_on=_id_list(row.get("depends_on", []), f"{task_id}.depends_on"),
                    conflict_keys=_id_list(
                        row.get("conflict_keys", []),
                        f"{task_id}.conflict_keys",
                    ),
                    required_capabilities=_id_list(
                        row.get("required_capabilities", []),
                        f"{task_id}.required_capabilities",
                    ),
                    estimated_effort=estimated,
                    max_attempts=attempts,
                    effect_class=effect,
                    approval_required=approval,
                )
            )

        tasks.sort(key=lambda item: item.task_id)
        order = _topological(tasks)
        source_digest = _digest(canonical_source)
        ir_material = {
            "workflow_id": workflow_id,
            "version": version,
            "source_digest": source_digest,
            "tasks": [task.as_dict() for task in tasks],
            "topological_order": list(order),
        }
        return CompiledWorkflow(
            workflow_id=workflow_id,
            version=version,
            source_digest=source_digest,
            ir_digest=_digest(ir_material),
            tasks=tuple(tasks),
            topological_order=order,
        )


def _critical_weights(workflow: CompiledWorkflow) -> dict[str, int]:
    by = workflow.task_map
    children: dict[str, set[str]] = {task_id: set() for task_id in by}
    for task in workflow.tasks:
        for dep in task.depends_on:
            children[dep].add(task.task_id)
    weight: dict[str, int] = {}
    for task_id in reversed(workflow.topological_order):
        downstream = max((weight[child] for child in children[task_id]), default=0)
        weight[task_id] = by[task_id].estimated_effort + downstream
    return weight


def critical_path(workflow: CompiledWorkflow) -> tuple[str, ...]:
    """Return the deterministic maximum-effort dependency path."""

    by = workflow.task_map
    children: dict[str, set[str]] = {task_id: set() for task_id in by}
    roots = set(by)
    for task in workflow.tasks:
        for dep in task.depends_on:
            children[dep].add(task.task_id)
            roots.discard(task.task_id)
    weight = _critical_weights(workflow)
    if not roots:
        raise WorkflowCompileError("workflow has no root task")
    current = sorted(roots, key=lambda task_id: (-weight[task_id], task_id))[0]
    path = [current]
    while children[current]:
        current = sorted(
            children[current],
            key=lambda task_id: (-weight[task_id], task_id),
        )[0]
        path.append(current)
    return tuple(path)


@dataclass(frozen=True, slots=True)
class ScheduleWave:
    index: int
    task_ids: tuple[str, ...]
    conflict_keys: tuple[str, ...]
    estimated_effort: int

    def as_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "task_ids": list(self.task_ids),
            "conflict_keys": list(self.conflict_keys),
            "estimated_effort": self.estimated_effort,
        }


@dataclass(frozen=True, slots=True)
class ScheduleSimulation:
    workflow_id: str
    ir_digest: str
    waves: tuple[ScheduleWave, ...]
    critical_path: tuple[str, ...]
    completed_order: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.workflow_schedule.v1",
            "workflow_id": self.workflow_id,
            "ir_digest": self.ir_digest,
            "waves": [wave.as_dict() for wave in self.waves],
            "critical_path": list(self.critical_path),
            "completed_order": list(self.completed_order),
        }


def simulate_schedule(
    workflow: CompiledWorkflow,
    *,
    max_concurrency: int = 4,
    precompleted: Iterable[str] = (),
) -> ScheduleSimulation:
    """Simulate deterministic dependency/conflict-aware execution waves."""

    if (
        isinstance(max_concurrency, bool)
        or not isinstance(max_concurrency, int)
        or not 1 <= max_concurrency <= 256
    ):
        raise ValueError("max_concurrency must be integer in [1,256]")
    by = workflow.task_map
    done = {_identifier(item, "precompleted") for item in precompleted}
    if not done <= set(by):
        unknown = sorted(done - set(by))
        raise WorkflowCompileError(f"unknown precompleted tasks: {unknown}")
    remaining = set(by) - done
    completed_order = list(
        task_id for task_id in workflow.topological_order if task_id in done
    )
    critical_weight = _critical_weights(workflow)
    waves: list[ScheduleWave] = []

    while remaining:
        candidates = [
            by[task_id]
            for task_id in remaining
            if set(by[task_id].depends_on) <= done
        ]
        if not candidates:
            raise WorkflowCompileError(
                "scheduler deadlock despite compiled acyclic workflow"
            )
        candidates.sort(
            key=lambda task: (-critical_weight[task.task_id], task.task_id)
        )
        selected: list[WorkflowTask] = []
        conflicts: set[str] = set()
        for task in candidates:
            task_conflicts = set(task.conflict_keys)
            if task_conflicts & conflicts:
                continue
            selected.append(task)
            conflicts.update(task_conflicts)
            if len(selected) >= max_concurrency:
                break
        if not selected:
            # Empty conflict keys are allowed, so this can only happen through
            # internal scheduler corruption.
            raise WorkflowCompileError("scheduler could not select a ready task")

        task_ids = tuple(task.task_id for task in selected)
        waves.append(
            ScheduleWave(
                index=len(waves),
                task_ids=task_ids,
                conflict_keys=tuple(sorted(conflicts)),
                estimated_effort=sum(task.estimated_effort for task in selected),
            )
        )
        for task_id in task_ids:
            remaining.remove(task_id)
            done.add(task_id)
            completed_order.append(task_id)

    return ScheduleSimulation(
        workflow_id=workflow.workflow_id,
        ir_digest=workflow.ir_digest,
        waves=tuple(waves),
        critical_path=critical_path(workflow),
        completed_order=tuple(completed_order),
    )


__all__ = [
    "CompiledWorkflow",
    "ScheduleSimulation",
    "ScheduleWave",
    "WorkflowCompileError",
    "WorkflowCompiler",
    "WorkflowTask",
    "critical_path",
    "simulate_schedule",
]
