"""Deterministic batch mutation planning with conflict detection and dry-run."""
from __future__ import annotations

import copy
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

from .canonical import digest
from .errors import BoundsError, CommandError, ValidationError
from .execution import CommandBuffer, CommandKind, CommitReceipt
from .store import EntityStore

MAX_BATCH_OPERATIONS = 50_000


class BatchOperationKind(str, Enum):
    CREATE_ENTITY = "create_entity"
    DELETE_ENTITY = "delete_entity"
    SET_COMPONENT = "set_component"
    PATCH_COMPONENT = "patch_component"
    REMOVE_COMPONENT = "remove_component"
    SET_RESOURCE = "set_resource"
    REMOVE_RESOURCE = "remove_resource"


@dataclass(frozen=True)
class BatchOperation:
    operation_id: str
    kind: BatchOperationKind
    payload: Mapping[str, Any]
    depends_on: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.operation_id, str) or not self.operation_id:
            raise ValidationError("batch operation id must be non-empty text")
        if not isinstance(self.kind, BatchOperationKind):
            try:
                object.__setattr__(self, "kind", BatchOperationKind(self.kind))
            except (TypeError, ValueError) as exc:
                raise ValidationError("unknown batch operation kind") from exc
        if not isinstance(self.payload, Mapping):
            raise ValidationError("batch operation payload must be mapping")
        deps = tuple(sorted(set(self.depends_on)))
        if self.operation_id in deps:
            raise ValidationError("batch operation cannot depend on itself")
        object.__setattr__(self, "depends_on", deps)

    @property
    def fingerprint(self) -> str:
        return digest(
            {
                "operation_id": self.operation_id,
                "kind": self.kind.value,
                "payload": dict(self.payload),
                "depends_on": self.depends_on,
            }
        )


@dataclass(frozen=True)
class BatchConflict:
    left_operation_id: str
    right_operation_id: str
    subject: str
    reason: str


@dataclass(frozen=True)
class BatchPlan:
    ordered_operations: tuple[BatchOperation, ...]
    conflicts: tuple[BatchConflict, ...]
    plan_digest: str

    @property
    def executable(self) -> bool:
        return not self.conflicts


@dataclass(frozen=True)
class DryRunResult:
    plan_digest: str
    before_digest: str
    after_digest: str
    before_revision: int
    after_revision: int
    changed: bool


@dataclass(frozen=True)
class BatchCommitResult:
    plan_digest: str
    receipt: CommitReceipt


class BatchPlanner:
    def __init__(self, operations: Iterable[BatchOperation] = ()) -> None:
        self._operations: dict[str, BatchOperation] = {}
        for operation in operations:
            self.add(operation)

    def add(self, operation: BatchOperation) -> BatchOperation:
        if not isinstance(operation, BatchOperation):
            raise ValidationError("batch planner requires BatchOperation")
        if operation.operation_id in self._operations:
            existing = self._operations[operation.operation_id]
            if existing.fingerprint != operation.fingerprint:
                raise ValidationError(
                    "batch operation id conflict",
                    context={"operation_id": operation.operation_id},
                )
            return existing
        if len(self._operations) >= MAX_BATCH_OPERATIONS:
            raise BoundsError(
                "batch operation bound exceeded",
                context={"maximum": MAX_BATCH_OPERATIONS},
            )
        self._operations[operation.operation_id] = operation
        return operation

    def operation_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._operations))

    def get(self, operation_id: str) -> BatchOperation:
        if operation_id not in self._operations:
            raise ValidationError(
                "batch operation not found",
                context={"operation_id": operation_id},
            )
        return self._operations[operation_id]

    def _ordered(self) -> tuple[BatchOperation, ...]:
        dependencies: dict[str, set[str]] = {
            operation_id: set(operation.depends_on)
            for operation_id, operation in self._operations.items()
        }
        for operation_id, deps in dependencies.items():
            missing = sorted(dep for dep in deps if dep not in self._operations)
            if missing:
                raise ValidationError(
                    "batch dependency not found",
                    context={"operation_id": operation_id, "missing": missing},
                )
        ordered: list[BatchOperation] = []
        remaining = {key: set(value) for key, value in dependencies.items()}
        while remaining:
            ready = sorted(key for key, deps in remaining.items() if not deps)
            if not ready:
                raise ValidationError(
                    "batch dependency cycle",
                    context={"remaining": sorted(remaining)},
                )
            for operation_id in ready:
                ordered.append(self._operations[operation_id])
                remaining.pop(operation_id)
            for deps in remaining.values():
                deps.difference_update(ready)
        return tuple(ordered)

    @staticmethod
    def _subject(operation: BatchOperation) -> tuple[str, str] | None:
        payload = operation.payload
        if operation.kind in {
            BatchOperationKind.SET_COMPONENT,
            BatchOperationKind.PATCH_COMPONENT,
            BatchOperationKind.REMOVE_COMPONENT,
        }:
            return (
                "component",
                f"{payload.get('entity_id')}::{payload.get('schema_id')}",
            )
        if operation.kind in {
            BatchOperationKind.CREATE_ENTITY,
            BatchOperationKind.DELETE_ENTITY,
        }:
            entity_id = payload.get("entity_id")
            if entity_id is not None:
                return ("entity", str(entity_id))
            return None
        if operation.kind in {
            BatchOperationKind.SET_RESOURCE,
            BatchOperationKind.REMOVE_RESOURCE,
        }:
            return ("resource", str(payload.get("resource_id")))
        return None

    def _dependency_closure(self) -> dict[str, set[str]]:
        closure = {
            operation_id: set(operation.depends_on)
            for operation_id, operation in self._operations.items()
        }
        changed = True
        while changed:
            changed = False
            for operation_id in sorted(closure):
                expanded = set(closure[operation_id])
                for dependency in tuple(expanded):
                    expanded.update(closure.get(dependency, ()))
                if expanded != closure[operation_id]:
                    closure[operation_id] = expanded
                    changed = True
        return closure

    def _conflicts(self, ordered: tuple[BatchOperation, ...]) -> tuple[BatchConflict, ...]:
        conflicts: list[BatchConflict] = []
        by_subject: dict[tuple[str, str], BatchOperation] = {}
        dependency_closure = self._dependency_closure()
        for operation in ordered:
            subject = self._subject(operation)
            if subject is None:
                continue
            prior = by_subject.get(subject)
            if prior is not None:
                explicitly_ordered = (
                    prior.operation_id in dependency_closure[operation.operation_id]
                    or operation.operation_id in dependency_closure[prior.operation_id]
                )
                if not explicitly_ordered:
                    conflicts.append(
                        BatchConflict(
                            left_operation_id=prior.operation_id,
                            right_operation_id=operation.operation_id,
                            subject=f"{subject[0]}:{subject[1]}",
                            reason="multiple mutations target the same subject without dependency ordering",
                        )
                    )
            by_subject[subject] = operation
        return tuple(conflicts)

    def plan(self) -> BatchPlan:
        ordered = self._ordered()
        conflicts = self._conflicts(ordered)
        material = {
            "domain": "skeleton.simulation.ecs.batch_plan.v1",
            "operations": [operation.fingerprint for operation in ordered],
            "conflicts": [conflict.__dict__ for conflict in conflicts],
        }
        return BatchPlan(
            ordered_operations=ordered,
            conflicts=conflicts,
            plan_digest=digest(material),
        )

    @staticmethod
    def _to_command(buffer: CommandBuffer, operation: BatchOperation) -> None:
        mapping = {
            BatchOperationKind.CREATE_ENTITY: CommandKind.CREATE_ENTITY,
            BatchOperationKind.DELETE_ENTITY: CommandKind.DELETE_ENTITY,
            BatchOperationKind.SET_COMPONENT: CommandKind.SET_COMPONENT,
            BatchOperationKind.PATCH_COMPONENT: CommandKind.PATCH_COMPONENT,
            BatchOperationKind.REMOVE_COMPONENT: CommandKind.REMOVE_COMPONENT,
            BatchOperationKind.SET_RESOURCE: CommandKind.SET_RESOURCE,
            BatchOperationKind.REMOVE_RESOURCE: CommandKind.REMOVE_RESOURCE,
        }
        buffer.add(
            mapping[operation.kind],
            copy.deepcopy(dict(operation.payload)),
            source=f"batch:{operation.operation_id}",
        )

    def _buffer(self, plan: BatchPlan) -> CommandBuffer:
        if not plan.executable:
            raise CommandError(
                "batch plan contains unresolved conflicts",
                context={"conflicts": len(plan.conflicts)},
            )
        buffer = CommandBuffer(max_commands=max(1, len(plan.ordered_operations)))
        for operation in plan.ordered_operations:
            self._to_command(buffer, operation)
        return buffer

    def dry_run(self, store: EntityStore) -> DryRunResult:
        plan = self.plan()
        clone = store.clone()
        before_digest = clone.state_digest
        before_revision = clone.revision
        buffer = self._buffer(plan)
        buffer.commit(clone)
        return DryRunResult(
            plan_digest=plan.plan_digest,
            before_digest=before_digest,
            after_digest=clone.state_digest,
            before_revision=before_revision,
            after_revision=clone.revision,
            changed=before_digest != clone.state_digest,
        )

    def commit(self, store: EntityStore) -> BatchCommitResult:
        plan = self.plan()
        receipt = self._buffer(plan).commit(store)
        return BatchCommitResult(plan_digest=plan.plan_digest, receipt=receipt)
