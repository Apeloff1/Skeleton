"""Crash-resumable orchestration for maintenance-gated orphan garbage collection.

The low-level orphan GC operator is intentionally stateless: it consumes one
exact plan under one active maintenance authority and returns a result.  This
module persists progress across that destructive sequence so a worker crash
after deleting some targets cannot force an operator to guess what happened.

Safety properties:

* one workflow binds one immutable parent GC plan digest;
* progress advances by CAS after every target outcome;
* every resumed target is executed through a fresh single-target child plan,
  preserving all live revalidation and maintenance checks in DurableOrphanGCOperator;
* if deletion succeeded but the worker crashed before progress persistence,
  retry observes the target as already absent and advances idempotently;
* operator-specific stale/manual-review outcomes become explicit workflow
  terminal states instead of being silently retried;
* maintenance lease failures are not converted into workflow authority.  The
  caller may obtain a fresh ORPHAN_GC maintenance epoch and retry resume.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import hashlib
import json
import math
import time
from typing import Callable

from skeleton.shells.ai.distributed_state import DistributedStateConflict
from skeleton.shells.ai.durable_maintenance import DurableMaintenanceGuard
from skeleton.shells.ai.durable_orphan_gc import (
    DurableOrphanDeleteResult,
    DurableOrphanGCManualReview,
    DurableOrphanGCOperator,
    DurableOrphanGCPlan,
    DurableOrphanGCResult,
    DurableOrphanGCStale,
)
from skeleton.shells.ai.store_protocol import VersionedStateBackend


def _digest(
    name: str,
    value: str,
) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{name} must be 64-character digest")
    return value.lower()


def _identity(
    name: str,
    value: str,
    *,
    maximum: int,
) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
    ):
        raise ValueError(f"invalid {name}")
    return value


def _timestamp(
    name: str,
    value: float,
) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0.0
    ):
        raise ValueError(
            f"{name} must be finite and non-negative"
        )
    return float(value)


class DurableOrphanWorkflowPhase(str, Enum):
    PLANNED = "planned"
    RUNNING = "running"
    COMPLETE = "complete"
    STALE = "stale"
    MANUAL_REVIEW = "manual_review"


@dataclass(frozen=True)
class DurableOrphanGCWorkflow:
    schema_version: int
    workflow_id: str
    chain_id: str
    parent_plan: DurableOrphanGCPlan
    phase: DurableOrphanWorkflowPhase
    next_target_index: int
    results: tuple[DurableOrphanDeleteResult, ...]
    created_at: float
    updated_at: float
    error_count: int = 0
    last_error_type: str = ""
    last_error_message: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(
                "unsupported orphan GC workflow schema"
            )
        object.__setattr__(
            self,
            "workflow_id",
            _digest(
                "workflow_id",
                self.workflow_id,
            ),
        )
        _identity(
            "chain_id",
            self.chain_id,
            maximum=128,
        )
        if not isinstance(
            self.parent_plan,
            DurableOrphanGCPlan,
        ):
            raise TypeError(
                "parent_plan must be DurableOrphanGCPlan"
            )
        if (
            self.parent_plan.chain_id
            != self.chain_id
        ):
            raise ValueError(
                "workflow chain differs from parent plan"
            )
        object.__setattr__(
            self,
            "phase",
            DurableOrphanWorkflowPhase(
                self.phase
            ),
        )
        if (
            isinstance(self.next_target_index, bool)
            or not isinstance(self.next_target_index, int)
            or self.next_target_index < 0
            or self.next_target_index
            > len(self.parent_plan.targets)
        ):
            raise ValueError(
                "next_target_index outside parent plan target range"
            )
        object.__setattr__(
            self,
            "results",
            tuple(self.results),
        )
        if len(self.results) != self.next_target_index:
            raise ValueError(
                "workflow result count must equal next_target_index"
            )
        for index, result in enumerate(
            self.results
        ):
            if not isinstance(
                result,
                DurableOrphanDeleteResult,
            ):
                raise TypeError(
                    "workflow results must contain DurableOrphanDeleteResult"
                )
            target = self.parent_plan.targets[
                index
            ]
            if (
                result.target_digest
                != target.digest
                or result.backend_key
                != target.backend_key
                or result.node_hash
                != target.node_hash
            ):
                raise ValueError(
                    "workflow result does not bind parent target"
                )
        object.__setattr__(
            self,
            "created_at",
            _timestamp(
                "created_at",
                self.created_at,
            ),
        )
        object.__setattr__(
            self,
            "updated_at",
            _timestamp(
                "updated_at",
                self.updated_at,
            ),
        )
        if self.updated_at < self.created_at:
            raise ValueError(
                "workflow updated_at precedes creation"
            )
        if (
            isinstance(self.error_count, bool)
            or not isinstance(self.error_count, int)
            or self.error_count < 0
        ):
            raise ValueError(
                "error_count must be non-negative integer"
            )
        if len(self.last_error_type) > 256:
            raise ValueError(
                "last_error_type too long"
            )
        if len(self.last_error_message) > 2048:
            raise ValueError(
                "last_error_message too long"
            )
        if bool(self.error_count) != bool(
            self.last_error_type
        ):
            raise ValueError(
                "error_count and last_error_type must be paired"
            )
        if (
            self.phase
            is DurableOrphanWorkflowPhase.COMPLETE
            and self.next_target_index
            != len(self.parent_plan.targets)
        ):
            raise ValueError(
                "complete workflow requires all targets processed"
            )
        if (
            self.phase
            in {
                DurableOrphanWorkflowPhase.STALE,
                DurableOrphanWorkflowPhase.MANUAL_REVIEW,
            }
            and not self.last_error_type
        ):
            raise ValueError(
                "terminal failed workflow requires error metadata"
            )
        expected_id = self.derive_id(
            self.parent_plan
        )
        if self.workflow_id != expected_id:
            raise ValueError(
                "workflow_id differs from parent plan binding"
            )

    @staticmethod
    def derive_id(
        plan: DurableOrphanGCPlan,
    ) -> str:
        if not isinstance(
            plan,
            DurableOrphanGCPlan,
        ):
            raise TypeError(
                "plan must be DurableOrphanGCPlan"
            )
        raw = json.dumps(
            {
                "authority": (
                    "durable-orphan-gc-workflow"
                ),
                "plan_id": plan.plan_id,
                "plan_digest": plan.digest,
                "chain_id": plan.chain_id,
                "node_kind": (
                    plan.node_kind.value
                ),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    @property
    def complete(self) -> bool:
        return (
            self.phase
            is DurableOrphanWorkflowPhase.COMPLETE
        )

    @property
    def terminal(self) -> bool:
        return self.phase in {
            DurableOrphanWorkflowPhase.COMPLETE,
            DurableOrphanWorkflowPhase.STALE,
            DurableOrphanWorkflowPhase.MANUAL_REVIEW,
        }

    @property
    def resumable(self) -> bool:
        return self.phase in {
            DurableOrphanWorkflowPhase.PLANNED,
            DurableOrphanWorkflowPhase.RUNNING,
        }

    @property
    def remaining_targets(self) -> int:
        return (
            len(self.parent_plan.targets)
            - self.next_target_index
        )

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(
                include_digest=False,
            ),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data: dict[str, object] = {
            "schema_version": self.schema_version,
            "workflow_id": self.workflow_id,
            "chain_id": self.chain_id,
            "parent_plan": (
                self.parent_plan.to_dict()
            ),
            "parent_plan_digest": (
                self.parent_plan.digest
            ),
            "phase": self.phase.value,
            "next_target_index": (
                self.next_target_index
            ),
            "total_targets": len(
                self.parent_plan.targets
            ),
            "remaining_targets": (
                self.remaining_targets
            ),
            "results": [
                item.to_dict()
                for item in self.results
            ],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error_count": self.error_count,
            "last_error_type": (
                self.last_error_type
            ),
            "last_error_message": (
                self.last_error_message
            ),
            "complete": self.complete,
            "terminal": self.terminal,
            "resumable": self.resumable,
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class StoredDurableOrphanGCWorkflow:
    revision: int
    workflow: DurableOrphanGCWorkflow

    def __post_init__(self) -> None:
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision <= 0
        ):
            raise ValueError(
                "workflow revision must be positive"
            )
        if not isinstance(
            self.workflow,
            DurableOrphanGCWorkflow,
        ):
            raise TypeError(
                "workflow must be DurableOrphanGCWorkflow"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "revision": self.revision,
            "workflow": (
                self.workflow.to_dict()
            ),
        }


class DurableOrphanWorkflowConflict(
    RuntimeError
):
    pass


class DurableOrphanGCWorkflowStore:
    """CAS store for crash-resumable orphan GC workflow progress."""

    def __init__(
        self,
        backend: VersionedStateBackend,
        *,
        namespace: str = "shell-ai-durable-orphan-gc-workflow",
        max_cas_retries: int = 32,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(
            backend,
            VersionedStateBackend,
        ):
            raise TypeError(
                "backend must satisfy VersionedStateBackend"
            )
        if not namespace or len(namespace) > 128:
            raise ValueError(
                "invalid orphan GC workflow namespace"
            )
        if (
            isinstance(max_cas_retries, bool)
            or not isinstance(max_cas_retries, int)
            or not 1 <= max_cas_retries <= 128
        ):
            raise ValueError(
                "max_cas_retries outside supported range"
            )
        if not callable(clock):
            raise TypeError(
                "clock must be callable"
            )
        self.backend = backend
        self.namespace = namespace
        self.max_cas_retries = max_cas_retries
        self._clock = clock

    @staticmethod
    def _key(
        workflow_id: str,
    ) -> str:
        return "workflow:" + _digest(
            "workflow_id",
            workflow_id,
        )

    def _now(self) -> float:
        return _timestamp(
            "workflow clock",
            self._clock(),
        )

    def current(
        self,
        workflow_id: str,
    ) -> StoredDurableOrphanGCWorkflow | None:
        record = self.backend.get(
            self.namespace,
            self._key(workflow_id),
        )
        if record is None:
            return None
        if not isinstance(
            record.value,
            DurableOrphanGCWorkflow,
        ):
            raise DurableOrphanWorkflowConflict(
                "orphan GC workflow value type mismatch"
            )
        if (
            record.value.workflow_id
            != workflow_id
        ):
            raise DurableOrphanWorkflowConflict(
                "orphan GC workflow key/value mismatch"
            )
        return StoredDurableOrphanGCWorkflow(
            record.revision,
            record.value,
        )

    def reserve(
        self,
        plan: DurableOrphanGCPlan,
    ) -> StoredDurableOrphanGCWorkflow:
        if not isinstance(
            plan,
            DurableOrphanGCPlan,
        ):
            raise TypeError(
                "plan must be DurableOrphanGCPlan"
            )
        workflow_id = (
            DurableOrphanGCWorkflow
            .derive_id(plan)
        )
        now = self._now()
        workflow = DurableOrphanGCWorkflow(
            1,
            workflow_id,
            plan.chain_id,
            plan,
            (
                DurableOrphanWorkflowPhase.COMPLETE
                if plan.empty
                else DurableOrphanWorkflowPhase.PLANNED
            ),
            0,
            (),
            now,
            now,
        )
        try:
            stored = self.backend.put_if_absent(
                self.namespace,
                self._key(workflow_id),
                workflow,
            )
            return StoredDurableOrphanGCWorkflow(
                stored.revision,
                workflow,
            )
        except DistributedStateConflict as exc:
            current = self.current(
                workflow_id
            )
            if current is None:
                raise
            if (
                current.workflow.parent_plan.digest
                != plan.digest
            ):
                raise DurableOrphanWorkflowConflict(
                    "workflow id already binds different parent plan"
                ) from exc
            return current

    def _replace(
        self,
        stored: StoredDurableOrphanGCWorkflow,
        updated: DurableOrphanGCWorkflow,
    ) -> StoredDurableOrphanGCWorkflow:
        if (
            stored.workflow.workflow_id
            != updated.workflow_id
        ):
            raise DurableOrphanWorkflowConflict(
                "workflow replacement identity mismatch"
            )
        try:
            result = self.backend.compare_and_swap(
                self.namespace,
                self._key(
                    updated.workflow_id
                ),
                expected_revision=(
                    stored.revision
                ),
                value=updated,
            )
            return StoredDurableOrphanGCWorkflow(
                result.revision,
                updated,
            )
        except DistributedStateConflict as exc:
            raise DurableOrphanWorkflowConflict(
                "orphan GC workflow revision conflict"
            ) from exc

    def mark_running(
        self,
        stored: StoredDurableOrphanGCWorkflow,
    ) -> StoredDurableOrphanGCWorkflow:
        if stored.workflow.terminal:
            return stored
        if (
            stored.workflow.phase
            is DurableOrphanWorkflowPhase.RUNNING
        ):
            return stored
        updated = replace(
            stored.workflow,
            phase=DurableOrphanWorkflowPhase.RUNNING,
            updated_at=self._now(),
        )
        return self._replace(
            stored,
            updated,
        )

    def append_result(
        self,
        stored: StoredDurableOrphanGCWorkflow,
        result: DurableOrphanDeleteResult,
    ) -> StoredDurableOrphanGCWorkflow:
        if not isinstance(
            result,
            DurableOrphanDeleteResult,
        ):
            raise TypeError(
                "result must be DurableOrphanDeleteResult"
            )
        workflow = stored.workflow
        if workflow.terminal:
            raise DurableOrphanWorkflowConflict(
                "terminal workflow cannot append result"
            )
        index = workflow.next_target_index
        if index >= len(
            workflow.parent_plan.targets
        ):
            raise DurableOrphanWorkflowConflict(
                "workflow has no remaining target"
            )
        target = workflow.parent_plan.targets[
            index
        ]
        if (
            result.target_digest
            != target.digest
            or result.backend_key
            != target.backend_key
            or result.node_hash
            != target.node_hash
        ):
            raise DurableOrphanWorkflowConflict(
                "workflow result differs from next target"
            )
        next_index = index + 1
        updated = replace(
            workflow,
            phase=(
                DurableOrphanWorkflowPhase.COMPLETE
                if next_index
                == len(
                    workflow.parent_plan.targets
                )
                else DurableOrphanWorkflowPhase.RUNNING
            ),
            next_target_index=next_index,
            results=workflow.results
            + (result,),
            updated_at=self._now(),
        )
        return self._replace(
            stored,
            updated,
        )

    def mark_failure(
        self,
        stored: StoredDurableOrphanGCWorkflow,
        *,
        phase: DurableOrphanWorkflowPhase,
        exc: BaseException,
    ) -> StoredDurableOrphanGCWorkflow:
        phase = DurableOrphanWorkflowPhase(
            phase
        )
        if phase not in {
            DurableOrphanWorkflowPhase.STALE,
            DurableOrphanWorkflowPhase.MANUAL_REVIEW,
        }:
            raise ValueError(
                "failure phase must be stale or manual_review"
            )
        if stored.workflow.complete:
            return stored
        message = str(exc)
        if len(message) > 2048:
            message = message[:2048]
        error_type = type(exc).__name__
        if len(error_type) > 256:
            error_type = error_type[:256]
        updated = replace(
            stored.workflow,
            phase=phase,
            updated_at=self._now(),
            error_count=(
                stored.workflow.error_count
                + 1
            ),
            last_error_type=error_type,
            last_error_message=message,
        )
        return self._replace(
            stored,
            updated,
        )


@dataclass(frozen=True)
class DurableOrphanWorkflowRun:
    before_revision: int
    after: StoredDurableOrphanGCWorkflow
    processed: int
    gc_results: tuple[
        DurableOrphanGCResult,
        ...]

    def __post_init__(self) -> None:
        if (
            isinstance(self.before_revision, bool)
            or not isinstance(self.before_revision, int)
            or self.before_revision <= 0
        ):
            raise ValueError(
                "before_revision must be positive"
            )
        if not isinstance(
            self.after,
            StoredDurableOrphanGCWorkflow,
        ):
            raise TypeError(
                "after must be StoredDurableOrphanGCWorkflow"
            )
        if (
            isinstance(self.processed, bool)
            or not isinstance(self.processed, int)
            or self.processed < 0
        ):
            raise ValueError(
                "processed must be non-negative integer"
            )
        object.__setattr__(
            self,
            "gc_results",
            tuple(self.gc_results),
        )
        if self.processed != len(
            self.gc_results
        ):
            raise ValueError(
                "processed count differs from gc_results"
            )

    @property
    def complete(self) -> bool:
        return self.after.workflow.complete

    def to_dict(self) -> dict[str, object]:
        return {
            "before_revision": (
                self.before_revision
            ),
            "after": self.after.to_dict(),
            "processed": self.processed,
            "gc_results": [
                item.to_dict()
                for item in self.gc_results
            ],
            "complete": self.complete,
        }


class DurableOrphanGCWorkflowCoordinator:
    """Resume an orphan cleanup workflow one durable target at a time."""

    def __init__(
        self,
        operator: DurableOrphanGCOperator,
        store: DurableOrphanGCWorkflowStore,
    ) -> None:
        if not isinstance(
            operator,
            DurableOrphanGCOperator,
        ):
            raise TypeError(
                "operator must be DurableOrphanGCOperator"
            )
        if not isinstance(
            store,
            DurableOrphanGCWorkflowStore,
        ):
            raise TypeError(
                "store must be DurableOrphanGCWorkflowStore"
            )
        self.operator = operator
        self.store = store

    @staticmethod
    def _child_plan(
        parent: DurableOrphanGCPlan,
        index: int,
    ) -> DurableOrphanGCPlan:
        target = parent.targets[
            index
        ]
        targets = (target,)
        plan_id = DurableOrphanGCPlan.derive_id(
            chain_id=parent.chain_id,
            node_kind=parent.node_kind,
            policy_digest=parent.policy_digest,
            scanner_policy_digest=(
                parent.scanner_policy_digest
            ),
            scan_digest=parent.scan_digest,
            head_sequence=parent.head_sequence,
            head_root=parent.head_root,
            floor_sequence=parent.floor_sequence,
            floor_root=parent.floor_root,
            floor_active=parent.floor_active,
            targets=targets,
            created_at=parent.created_at,
        )
        return DurableOrphanGCPlan(
            1,
            plan_id,
            parent.chain_id,
            parent.node_kind,
            parent.policy_digest,
            parent.scanner_policy_digest,
            parent.scan_digest,
            parent.head_sequence,
            parent.head_root,
            parent.floor_sequence,
            parent.floor_root,
            parent.floor_active,
            targets,
            parent.created_at,
        )

    def start(
        self,
        plan: DurableOrphanGCPlan,
    ) -> StoredDurableOrphanGCWorkflow:
        return self.store.reserve(
            plan
        )

    def resume(
        self,
        workflow_id: str,
        chain: object,
        *,
        maintenance: DurableMaintenanceGuard,
        max_targets: int = 64,
    ) -> DurableOrphanWorkflowRun:
        workflow_id = _digest(
            "workflow_id",
            workflow_id,
        )
        if (
            isinstance(max_targets, bool)
            or not isinstance(max_targets, int)
            or max_targets <= 0
            or max_targets > 4096
        ):
            raise ValueError(
                "max_targets outside supported workflow range"
            )
        stored = self.store.current(
            workflow_id
        )
        if stored is None:
            raise DurableOrphanWorkflowConflict(
                "orphan GC workflow is missing"
            )
        before_revision = stored.revision
        if not stored.workflow.resumable:
            return DurableOrphanWorkflowRun(
                before_revision,
                stored,
                0,
                (),
            )
        stored = self.store.mark_running(
            stored
        )

        gc_results: list[
            DurableOrphanGCResult
        ] = []
        processed = 0
        while (
            stored.workflow.resumable
            and processed < max_targets
        ):
            index = (
                stored.workflow
                .next_target_index
            )
            if index >= len(
                stored.workflow
                .parent_plan.targets
            ):
                break
            child = self._child_plan(
                stored.workflow.parent_plan,
                index,
            )
            try:
                gc_result = (
                    self.operator.execute(
                        child,
                        chain,
                        maintenance=maintenance,
                    )
                )
            except DurableOrphanGCStale as exc:
                stored = self.store.mark_failure(
                    stored,
                    phase=(
                        DurableOrphanWorkflowPhase.STALE
                    ),
                    exc=exc,
                )
                break
            except DurableOrphanGCManualReview as exc:
                stored = self.store.mark_failure(
                    stored,
                    phase=(
                        DurableOrphanWorkflowPhase.MANUAL_REVIEW
                    ),
                    exc=exc,
                )
                break

            if len(gc_result.results) != 1:
                raise DurableOrphanWorkflowConflict(
                    "single-target child GC returned unexpected result count"
                )
            stored = self.store.append_result(
                stored,
                gc_result.results[0],
            )
            gc_results.append(
                gc_result
            )
            processed += 1

        return DurableOrphanWorkflowRun(
            before_revision,
            stored,
            processed,
            tuple(gc_results),
        )

    def inspect(
        self,
        workflow_id: str,
    ) -> StoredDurableOrphanGCWorkflow:
        workflow_id = _digest(
            "workflow_id",
            workflow_id,
        )
        stored = self.store.current(
            workflow_id
        )
        if stored is None:
            raise DurableOrphanWorkflowConflict(
                "orphan GC workflow is missing"
            )
        return stored
