"""Cross-chain durable compaction coordination.

Journal and receipt chains are independently fenced durable evidence chains.
They cannot be made transactionally atomic by pretending two separate hot-floor
commits are one database transaction.  This module instead implements an
explicit durable saga:

1. every member workflow is planned and bound into one group intent;
2. every member must be certified before destructive authority is issued;
3. every member must be authorized before any delete manifest is frozen;
4. every member manifest must be frozen before any hot floor may advance;
5. member execution progress is persisted after each chain;
6. asymmetric floor advancement is reported as PARTIAL_COMMIT and requires an
   explicit resume call;
7. authority substitution, missing member state, or manual-review members move
   the whole group to MANUAL_REVIEW.

The coordinator never widens a member's authority.  Each chain still relies on
its own compaction certificate, pruning authorization, manifest, fencing lease,
hot-floor signature, and archive continuity checks.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import hashlib
import json
import math
import time
from typing import Callable, Mapping, Sequence

from skeleton.shells.ai.distributed_state import DistributedStateConflict
from skeleton.shells.ai.durable_checkpoint import CheckpointableEvidenceChain
from skeleton.shells.ai.durable_compaction_operator import (
    DurableCompactionExecution,
    DurableCompactionOperator,
    DurableCompactionPrepared,
    DurableCompactionWorkflowError,
    DurableCompactionWorkflowManualReview,
    DurableCompactionWorkflowPhase,
    DurableCompactionWorkflowStale,
)
from skeleton.shells.ai.durable_retention import DurableRetentionPlan
from skeleton.shells.ai.store_protocol import VersionedStateBackend


def _digest(
    name: str,
    value: str,
    *,
    optional: bool = False,
) -> str:
    if optional and not value:
        return ""
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


class DurableCompactionGroupPhase(str, Enum):
    PLANNED = "planned"
    CERTIFIED = "certified"
    AUTHORIZED = "authorized"
    PREPARED = "prepared"
    EXECUTING = "executing"
    PARTIAL_COMMIT = "partial_commit"
    COMPLETE = "complete"
    MANUAL_REVIEW = "manual_review"


_PHASE_ORDER = {
    DurableCompactionGroupPhase.PLANNED: 10,
    DurableCompactionGroupPhase.CERTIFIED: 20,
    DurableCompactionGroupPhase.AUTHORIZED: 30,
    DurableCompactionGroupPhase.PREPARED: 40,
    DurableCompactionGroupPhase.EXECUTING: 50,
    DurableCompactionGroupPhase.PARTIAL_COMMIT: 55,
    DurableCompactionGroupPhase.COMPLETE: 60,
    DurableCompactionGroupPhase.MANUAL_REVIEW: 90,
}


@dataclass(frozen=True)
class DurableCompactionGroupRequest:
    chain_id: str
    operator: DurableCompactionOperator
    retention: DurableRetentionPlan
    chain: CheckpointableEvidenceChain

    def __post_init__(self) -> None:
        _identity(
            "chain_id",
            self.chain_id,
            maximum=128,
        )
        if not isinstance(
            self.operator,
            DurableCompactionOperator,
        ):
            raise TypeError(
                "operator must be DurableCompactionOperator"
            )
        if not isinstance(
            self.retention,
            DurableRetentionPlan,
        ):
            raise TypeError(
                "retention must be DurableRetentionPlan"
            )
        if not isinstance(
            self.chain,
            CheckpointableEvidenceChain,
        ):
            raise TypeError(
                "chain must satisfy CheckpointableEvidenceChain"
            )
        if self.retention.chain_id != self.chain_id:
            raise ValueError(
                "retention chain_id differs from group request"
            )


@dataclass(frozen=True)
class DurableCompactionGroupMember:
    chain_id: str
    workflow_id: str
    workflow_binding_digest: str
    retention_plan_digest: str
    current_sequence: int
    current_root: str
    cutoff_sequence: int
    cutoff_root: str
    previous_floor_sequence: int
    previous_floor_root: str
    archive_id: str
    archive_manifest_digest: str
    certificate_id: str = ""
    authorization_id: str = ""
    pruning_operation_id: str = ""
    pruning_manifest_digest: str = ""
    floor_id: str = ""
    workflow_phase: str = DurableCompactionWorkflowPhase.PLANNED.value
    deleted_items: int = 0
    delete_count: int = 0

    def __post_init__(self) -> None:
        _identity(
            "chain_id",
            self.chain_id,
            maximum=128,
        )
        for name in (
            "workflow_id",
            "workflow_binding_digest",
            "retention_plan_digest",
            "current_root",
            "cutoff_root",
            "previous_floor_root",
            "archive_manifest_digest",
        ):
            object.__setattr__(
                self,
                name,
                _digest(name, getattr(self, name)),
            )
        for name in (
            "certificate_id",
            "authorization_id",
            "pruning_operation_id",
            "pruning_manifest_digest",
            "floor_id",
        ):
            object.__setattr__(
                self,
                name,
                _digest(
                    name,
                    getattr(self, name),
                    optional=True,
                ),
            )
        _identity(
            "archive_id",
            self.archive_id,
            maximum=256,
        )
        phase = DurableCompactionWorkflowPhase(
            self.workflow_phase
        )
        object.__setattr__(
            self,
            "workflow_phase",
            phase.value,
        )
        for name in (
            "current_sequence",
            "cutoff_sequence",
            "previous_floor_sequence",
            "deleted_items",
            "delete_count",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise ValueError(
                    f"{name} must be non-negative integer"
                )
        if self.cutoff_sequence <= 0:
            raise ValueError(
                "group member cutoff_sequence must be positive"
            )
        if self.cutoff_sequence > self.current_sequence:
            raise ValueError(
                "group member cutoff exceeds current sequence"
            )
        if (
            self.previous_floor_sequence
            >= self.cutoff_sequence
        ):
            raise ValueError(
                "group member cutoff must advance previous floor"
            )
        if (
            self.previous_floor_sequence == 0
            and self.previous_floor_root != "0" * 64
        ):
            raise ValueError(
                "group member genesis floor must use genesis root"
            )
        if self.deleted_items > self.delete_count:
            raise ValueError(
                "group member deleted_items exceeds delete_count"
            )

    @property
    def floor_committed(self) -> bool:
        return bool(self.floor_id)

    @property
    def complete(self) -> bool:
        return (
            self.workflow_phase
            == DurableCompactionWorkflowPhase.COMPLETE.value
        )

    @property
    def manual_review(self) -> bool:
        return (
            self.workflow_phase
            == DurableCompactionWorkflowPhase.MANUAL_REVIEW.value
        )

    @property
    def prepared(self) -> bool:
        return bool(
            self.pruning_operation_id
            and self.pruning_manifest_digest
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "chain_id": self.chain_id,
            "workflow_id": self.workflow_id,
            "workflow_binding_digest": (
                self.workflow_binding_digest
            ),
            "retention_plan_digest": (
                self.retention_plan_digest
            ),
            "current_sequence": self.current_sequence,
            "current_root": self.current_root,
            "cutoff_sequence": self.cutoff_sequence,
            "cutoff_root": self.cutoff_root,
            "previous_floor_sequence": (
                self.previous_floor_sequence
            ),
            "previous_floor_root": (
                self.previous_floor_root
            ),
            "archive_id": self.archive_id,
            "archive_manifest_digest": (
                self.archive_manifest_digest
            ),
            "certificate_id": self.certificate_id,
            "authorization_id": self.authorization_id,
            "pruning_operation_id": (
                self.pruning_operation_id
            ),
            "pruning_manifest_digest": (
                self.pruning_manifest_digest
            ),
            "floor_id": self.floor_id,
            "workflow_phase": self.workflow_phase,
            "deleted_items": self.deleted_items,
            "delete_count": self.delete_count,
            "floor_committed": self.floor_committed,
            "complete": self.complete,
            "manual_review": self.manual_review,
            "prepared": self.prepared,
        }


@dataclass(frozen=True)
class DurableCompactionGroup:
    schema_version: int
    group_id: str
    epoch_id: str
    operator_id: str
    phase: DurableCompactionGroupPhase
    members: tuple[DurableCompactionGroupMember, ...]
    created_at: float
    updated_at: float
    next_member_index: int = 0
    completed_members: int = 0
    error_count: int = 0
    last_error: str = ""
    last_error_at: float = 0.0

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(
                "unsupported compaction group schema"
            )
        object.__setattr__(
            self,
            "group_id",
            _digest("group_id", self.group_id),
        )
        _identity(
            "epoch_id",
            self.epoch_id,
            maximum=256,
        )
        _identity(
            "operator_id",
            self.operator_id,
            maximum=256,
        )
        object.__setattr__(
            self,
            "phase",
            DurableCompactionGroupPhase(
                self.phase
            ),
        )
        members = tuple(self.members)
        if len(members) < 2:
            raise ValueError(
                "compaction group requires at least two members"
            )
        chain_ids = tuple(
            member.chain_id
            for member in members
        )
        if (
            chain_ids
            != tuple(sorted(chain_ids))
            or len(chain_ids)
            != len(set(chain_ids))
        ):
            raise ValueError(
                "compaction group members must be uniquely sorted by chain_id"
            )
        object.__setattr__(
            self,
            "members",
            members,
        )
        for name in (
            "next_member_index",
            "completed_members",
            "error_count",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise ValueError(
                    f"{name} must be non-negative integer"
                )
        if self.next_member_index > len(members):
            raise ValueError(
                "next_member_index exceeds member count"
            )
        if self.completed_members > len(members):
            raise ValueError(
                "completed_members exceeds member count"
            )
        actual_complete = sum(
            1 for member in members
            if member.complete
        )
        if self.completed_members != actual_complete:
            raise ValueError(
                "completed_members differs from member state"
            )
        for name in (
            "created_at",
            "updated_at",
            "last_error_at",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) < 0.0
            ):
                raise ValueError(
                    f"{name} must be finite and non-negative"
                )
            object.__setattr__(
                self,
                name,
                float(value),
            )
        if self.updated_at < self.created_at:
            raise ValueError(
                "group updated_at precedes creation"
            )
        if self.error_count:
            if not self.last_error:
                raise ValueError(
                    "group error_count requires last_error"
                )
            if self.last_error_at <= 0:
                raise ValueError(
                    "group error_count requires last_error_at"
                )
        elif self.last_error or self.last_error_at:
            raise ValueError(
                "group error fields require error_count"
            )
        if len(self.last_error) > 2048:
            raise ValueError(
                "group last_error is too long"
            )
        if self.phase is DurableCompactionGroupPhase.COMPLETE:
            if self.completed_members != len(members):
                raise ValueError(
                    "complete group requires every member complete"
                )
        if self.phase is DurableCompactionGroupPhase.PREPARED:
            if not all(
                member.prepared
                for member in members
            ):
                raise ValueError(
                    "prepared group requires every member manifest frozen"
                )
        if self.phase is DurableCompactionGroupPhase.CERTIFIED:
            if not all(
                member.certificate_id
                for member in members
            ):
                raise ValueError(
                    "certified group requires every certificate"
                )
        if self.phase is DurableCompactionGroupPhase.AUTHORIZED:
            if not all(
                member.authorization_id
                for member in members
            ):
                raise ValueError(
                    "authorized group requires every authorization"
                )

    @property
    def partial_commit(self) -> bool:
        committed = sum(
            1
            for member in self.members
            if member.floor_committed
            or member.complete
        )
        return 0 < committed < len(self.members)

    @property
    def complete(self) -> bool:
        return (
            self.phase
            is DurableCompactionGroupPhase.COMPLETE
        )

    @property
    def requires_manual_review(self) -> bool:
        return (
            self.phase
            is DurableCompactionGroupPhase.MANUAL_REVIEW
            or any(
                member.manual_review
                for member in self.members
            )
        )

    @property
    def resumable(self) -> bool:
        return (
            self.phase
            in {
                DurableCompactionGroupPhase.EXECUTING,
                DurableCompactionGroupPhase.PARTIAL_COMMIT,
            }
            and not self.requires_manual_review
        )

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(include_digest=False),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    @property
    def binding_digest(self) -> str:
        raw = json.dumps(
            {
                "group_id": self.group_id,
                "epoch_id": self.epoch_id,
                "operator_id": self.operator_id,
                "members": [
                    {
                        "chain_id": member.chain_id,
                        "workflow_id": member.workflow_id,
                        "workflow_binding_digest": (
                            member.workflow_binding_digest
                        ),
                        "retention_plan_digest": (
                            member.retention_plan_digest
                        ),
                    }
                    for member in self.members
                ],
            },
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
            "group_id": self.group_id,
            "epoch_id": self.epoch_id,
            "operator_id": self.operator_id,
            "phase": self.phase.value,
            "members": [
                member.to_dict()
                for member in self.members
            ],
            "next_member_index": self.next_member_index,
            "completed_members": self.completed_members,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error_count": self.error_count,
            "last_error": self.last_error,
            "last_error_at": self.last_error_at,
            "partial_commit": self.partial_commit,
            "complete": self.complete,
            "requires_manual_review": (
                self.requires_manual_review
            ),
            "resumable": self.resumable,
            "binding_digest": self.binding_digest,
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class StoredDurableCompactionGroup:
    revision: int
    group: DurableCompactionGroup

    def __post_init__(self) -> None:
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision <= 0
        ):
            raise ValueError(
                "group revision must be positive"
            )
        if not isinstance(
            self.group,
            DurableCompactionGroup,
        ):
            raise TypeError(
                "group must be DurableCompactionGroup"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "revision": self.revision,
            "group": self.group.to_dict(),
        }


@dataclass(frozen=True)
class DurableCompactionGroupInspection:
    stored: StoredDurableCompactionGroup
    member_current: tuple[tuple[str, bool], ...]
    member_floor_committed: tuple[tuple[str, bool], ...]
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "member_current",
            tuple(self.member_current),
        )
        object.__setattr__(
            self,
            "member_floor_committed",
            tuple(self.member_floor_committed),
        )
        object.__setattr__(
            self,
            "reasons",
            tuple(self.reasons),
        )

    @property
    def current(self) -> bool:
        return (
            all(value for _, value in self.member_current)
            and not self.reasons
        )

    @property
    def partial_commit(self) -> bool:
        values = tuple(
            value
            for _, value
            in self.member_floor_committed
        )
        return any(values) and not all(values)

    @property
    def safe_to_execute(self) -> bool:
        return (
            self.current
            and self.stored.group.phase
            is DurableCompactionGroupPhase.PREPARED
            and not self.partial_commit
        )

    @property
    def safe_to_resume(self) -> bool:
        return (
            self.stored.group.resumable
            and not self.stored.group.requires_manual_review
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "stored": self.stored.to_dict(),
            "current": self.current,
            "partial_commit": self.partial_commit,
            "safe_to_execute": self.safe_to_execute,
            "safe_to_resume": self.safe_to_resume,
            "member_current": [
                {
                    "chain_id": chain_id,
                    "current": current,
                }
                for chain_id, current
                in self.member_current
            ],
            "member_floor_committed": [
                {
                    "chain_id": chain_id,
                    "floor_committed": committed,
                }
                for chain_id, committed
                in self.member_floor_committed
            ],
            "reasons": list(self.reasons),
        }


class DurableCompactionGroupError(RuntimeError):
    pass


class DurableCompactionGroupManualReview(
    DurableCompactionGroupError
):
    pass


class DurableCompactionGroupStale(
    DurableCompactionGroupError
):
    pass


class DurableCompactionGroupCoordinator:
    """Coordinate several durable compaction workflows as one explicit saga."""

    def __init__(
        self,
        backend: VersionedStateBackend,
        *,
        namespace: str = (
            "shell-ai-durable-compaction-groups"
        ),
        max_members: int = 16,
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
        if (
            not namespace
            or len(namespace) > 128
        ):
            raise ValueError(
                "invalid compaction group namespace"
            )
        if (
            isinstance(max_members, bool)
            or not isinstance(max_members, int)
            or not 2 <= max_members <= 64
        ):
            raise ValueError(
                "max_members outside supported range"
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
            raise TypeError("clock must be callable")
        self.backend = backend
        self.namespace = namespace
        self.max_members = max_members
        self.max_cas_retries = max_cas_retries
        self._clock = clock

    @staticmethod
    def _key(group_id: str) -> str:
        return (
            "group:"
            + _digest("group_id", group_id)
        )

    def _now(self) -> float:
        value = self._clock()
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or float(value) < 0
        ):
            raise DurableCompactionGroupError(
                "group clock returned invalid time"
            )
        return float(value)

    @staticmethod
    def _request_map(
        requests: Sequence[
            DurableCompactionGroupRequest
        ],
    ) -> dict[
        str,
        DurableCompactionGroupRequest,
    ]:
        result: dict[
            str,
            DurableCompactionGroupRequest,
        ] = {}
        for request in requests:
            if not isinstance(
                request,
                DurableCompactionGroupRequest,
            ):
                raise TypeError(
                    "requests must contain DurableCompactionGroupRequest"
                )
            if request.chain_id in result:
                raise ValueError(
                    "duplicate chain_id in compaction group"
                )
            result[request.chain_id] = request
        return result

    @staticmethod
    def derive_group_id(
        *,
        epoch_id: str,
        operator_id: str,
        members: Sequence[
            DurableCompactionGroupMember
        ],
    ) -> str:
        epoch_id = _identity(
            "epoch_id",
            epoch_id,
            maximum=256,
        )
        operator_id = _identity(
            "operator_id",
            operator_id,
            maximum=256,
        )
        ordered = tuple(
            sorted(
                members,
                key=lambda item: item.chain_id,
            )
        )
        if len(ordered) < 2:
            raise ValueError(
                "group id requires at least two members"
            )
        raw = json.dumps(
            {
                "epoch_id": epoch_id,
                "operator_id": operator_id,
                "members": [
                    {
                        "chain_id": member.chain_id,
                        "workflow_id": member.workflow_id,
                        "workflow_binding_digest": (
                            member.workflow_binding_digest
                        ),
                        "retention_plan_digest": (
                            member.retention_plan_digest
                        ),
                    }
                    for member in ordered
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def current(
        self,
        group_id: str,
    ) -> StoredDurableCompactionGroup | None:
        record = self.backend.get(
            self.namespace,
            self._key(group_id),
        )
        if record is None:
            return None
        if not isinstance(
            record.value,
            DurableCompactionGroup,
        ):
            raise DurableCompactionGroupError(
                "group backend value type mismatch"
            )
        return StoredDurableCompactionGroup(
            record.revision,
            record.value,
        )

    def _create(
        self,
        group: DurableCompactionGroup,
    ) -> StoredDurableCompactionGroup:
        try:
            record = self.backend.put_if_absent(
                self.namespace,
                self._key(group.group_id),
                group,
            )
            return StoredDurableCompactionGroup(
                record.revision,
                group,
            )
        except DistributedStateConflict:
            existing = self.current(
                group.group_id
            )
            if existing is None:
                raise
            if (
                existing.group.binding_digest
                != group.binding_digest
            ):
                raise DurableCompactionGroupError(
                    "group id already binds different member authority"
                )
            return existing

    def _replace(
        self,
        expected: DurableCompactionGroup,
        **changes,
    ) -> StoredDurableCompactionGroup:
        key = self._key(
            expected.group_id
        )
        for _ in range(
            self.max_cas_retries
        ):
            record = self.backend.get(
                self.namespace,
                key,
            )
            if record is None:
                raise DurableCompactionGroupError(
                    "compaction group is missing"
                )
            current = record.value
            if not isinstance(
                current,
                DurableCompactionGroup,
            ):
                raise DurableCompactionGroupError(
                    "group backend value type mismatch"
                )
            if (
                current.binding_digest
                != expected.binding_digest
            ):
                raise DurableCompactionGroupError(
                    "group member authority binding changed"
                )
            requested_phase = (
                DurableCompactionGroupPhase(
                    changes.get(
                        "phase",
                        current.phase,
                    )
                )
            )
            if (
                current.phase
                is DurableCompactionGroupPhase.MANUAL_REVIEW
                and requested_phase
                is not DurableCompactionGroupPhase.MANUAL_REVIEW
            ):
                raise DurableCompactionGroupManualReview(
                    "manual-review group cannot advance automatically"
                )
            if (
                current.phase
                is DurableCompactionGroupPhase.COMPLETE
                and requested_phase
                is not DurableCompactionGroupPhase.COMPLETE
            ):
                raise DurableCompactionGroupError(
                    "complete group cannot regress"
                )
            if (
                requested_phase
                is not DurableCompactionGroupPhase.MANUAL_REVIEW
                and _PHASE_ORDER[requested_phase]
                < _PHASE_ORDER[current.phase]
            ):
                return StoredDurableCompactionGroup(
                    record.revision,
                    current,
                )
            updated = replace(
                current,
                updated_at=self._now(),
                **changes,
            )
            if updated == current:
                return StoredDurableCompactionGroup(
                    record.revision,
                    current,
                )
            try:
                stored = self.backend.compare_and_swap(
                    self.namespace,
                    key,
                    expected_revision=record.revision,
                    value=updated,
                )
                return StoredDurableCompactionGroup(
                    stored.revision,
                    updated,
                )
            except DistributedStateConflict:
                continue
        raise DurableCompactionGroupError(
            "group CAS retry budget exhausted"
        )

    def _note_error(
        self,
        group: DurableCompactionGroup,
        exc: BaseException,
        *,
        manual_review: bool,
        partial_commit: bool = False,
    ) -> StoredDurableCompactionGroup:
        phase = (
            DurableCompactionGroupPhase.MANUAL_REVIEW
            if manual_review
            else (
                DurableCompactionGroupPhase.PARTIAL_COMMIT
                if partial_commit
                else group.phase
            )
        )
        return self._replace(
            group,
            phase=phase,
            error_count=group.error_count + 1,
            last_error=(
                f"{type(exc).__name__}: {exc}"
            )[:2048],
            last_error_at=self._now(),
        )

    @staticmethod
    def _member_from_workflow(
        workflow,
    ) -> DurableCompactionGroupMember:
        return DurableCompactionGroupMember(
            workflow.chain_id,
            workflow.workflow_id,
            workflow.binding_digest,
            workflow.retention_plan_digest,
            workflow.current_sequence,
            workflow.current_root,
            workflow.cutoff_sequence,
            workflow.cutoff_root,
            workflow.previous_floor_sequence,
            workflow.previous_floor_root,
            workflow.archive_id,
            workflow.archive_manifest_digest,
            certificate_id=(
                workflow.certificate_id
            ),
            authorization_id=(
                workflow.authorization_id
            ),
            pruning_operation_id=(
                workflow.pruning_operation_id
            ),
            pruning_manifest_digest=(
                workflow.pruning_manifest_digest
            ),
            floor_id=workflow.floor_id,
            workflow_phase=(
                workflow.phase.value
            ),
            deleted_items=(
                workflow.deleted_items
            ),
            delete_count=workflow.delete_count,
        )

    @classmethod
    def _sync_members(
        cls,
        group: DurableCompactionGroup,
        request_map: Mapping[
            str,
            DurableCompactionGroupRequest,
        ],
    ) -> tuple[
        DurableCompactionGroupMember,
        ...,
    ]:
        members = []
        for member in group.members:
            request = request_map.get(
                member.chain_id
            )
            if request is None:
                raise DurableCompactionGroupError(
                    "group request set is missing a member chain"
                )
            stored = request.operator.current(
                member.workflow_id
            )
            if stored is None:
                raise DurableCompactionGroupManualReview(
                    "group member workflow is missing"
                )
            workflow = stored.workflow
            if (
                workflow.binding_digest
                != member.workflow_binding_digest
                or workflow.retention_plan_digest
                != member.retention_plan_digest
            ):
                raise DurableCompactionGroupManualReview(
                    "group member workflow authority binding changed"
                )
            members.append(
                cls._member_from_workflow(
                    workflow
                )
            )
        return tuple(members)

    def _require_requests(
        self,
        group: DurableCompactionGroup,
        requests: Sequence[
            DurableCompactionGroupRequest
        ],
    ) -> dict[
        str,
        DurableCompactionGroupRequest,
    ]:
        request_map = self._request_map(
            requests
        )
        if (
            set(request_map)
            != {
                member.chain_id
                for member in group.members
            }
        ):
            raise DurableCompactionGroupError(
                "request set differs from persisted group membership"
            )
        for member in group.members:
            request = request_map[
                member.chain_id
            ]
            if (
                request.retention.digest
                != member.retention_plan_digest
            ):
                raise DurableCompactionGroupStale(
                    "member retention plan differs from group binding"
                )
        return request_map

    def plan(
        self,
        requests: Sequence[
            DurableCompactionGroupRequest
        ],
        *,
        epoch_id: str,
        operator_id: str,
    ) -> StoredDurableCompactionGroup:
        epoch_id = _identity(
            "epoch_id",
            epoch_id,
            maximum=256,
        )
        operator_id = _identity(
            "operator_id",
            operator_id,
            maximum=256,
        )
        request_map = self._request_map(
            requests
        )
        if not 2 <= len(request_map) <= self.max_members:
            raise ValueError(
                "group member count outside supported range"
            )

        members = []
        for chain_id in sorted(
            request_map
        ):
            request = request_map[
                chain_id
            ]
            plan = request.operator.plan(
                request.retention,
                request.chain,
                operator_id=operator_id,
            )
            members.append(
                self._member_from_workflow(
                    plan.stored.workflow
                )
            )
        members_tuple = tuple(members)
        group_id = self.derive_group_id(
            epoch_id=epoch_id,
            operator_id=operator_id,
            members=members_tuple,
        )
        now = self._now()
        group = DurableCompactionGroup(
            1,
            group_id,
            epoch_id,
            operator_id,
            DurableCompactionGroupPhase.PLANNED,
            members_tuple,
            now,
            now,
            next_member_index=0,
            completed_members=0,
        )
        return self._create(group)

    def _require_group(
        self,
        group_id: str,
    ) -> StoredDurableCompactionGroup:
        stored = self.current(group_id)
        if stored is None:
            raise DurableCompactionGroupError(
                "compaction group is missing"
            )
        if stored.group.requires_manual_review:
            raise DurableCompactionGroupManualReview(
                stored.group.last_error
                or "compaction group requires manual review"
            )
        return stored

    def certify_all(
        self,
        group_id: str,
        requests: Sequence[
            DurableCompactionGroupRequest
        ],
    ) -> StoredDurableCompactionGroup:
        stored = self._require_group(
            group_id
        )
        group = stored.group
        if (
            _PHASE_ORDER[group.phase]
            > _PHASE_ORDER[
                DurableCompactionGroupPhase.CERTIFIED
            ]
        ):
            return stored
        request_map = self._require_requests(
            group,
            requests,
        )
        for member in group.members:
            request = request_map[
                member.chain_id
            ]
            request.operator.certify(
                member.workflow_id,
                request.retention,
                request.chain,
            )
        synced = self._sync_members(
            group,
            request_map,
        )
        if not all(
            member.certificate_id
            for member in synced
        ):
            raise DurableCompactionGroupError(
                "not every group member acquired a certificate"
            )
        return self._replace(
            group,
            phase=(
                DurableCompactionGroupPhase.CERTIFIED
            ),
            members=synced,
        )

    def authorize_all(
        self,
        group_id: str,
        requests: Sequence[
            DurableCompactionGroupRequest
        ],
    ) -> StoredDurableCompactionGroup:
        stored = self._require_group(
            group_id
        )
        group = stored.group
        if (
            _PHASE_ORDER[group.phase]
            < _PHASE_ORDER[
                DurableCompactionGroupPhase.CERTIFIED
            ]
        ):
            raise DurableCompactionGroupError(
                "group must be certified before authorization"
            )
        if (
            _PHASE_ORDER[group.phase]
            > _PHASE_ORDER[
                DurableCompactionGroupPhase.AUTHORIZED
            ]
        ):
            return stored
        request_map = self._require_requests(
            group,
            requests,
        )
        for member in group.members:
            request = request_map[
                member.chain_id
            ]
            request.operator.authorize(
                member.workflow_id,
                request.retention,
                request.chain,
            )
        synced = self._sync_members(
            group,
            request_map,
        )
        if not all(
            member.authorization_id
            for member in synced
        ):
            raise DurableCompactionGroupError(
                "not every group member acquired destructive authority"
            )
        return self._replace(
            group,
            phase=(
                DurableCompactionGroupPhase.AUTHORIZED
            ),
            members=synced,
        )

    def prepare_all(
        self,
        group_id: str,
        requests: Sequence[
            DurableCompactionGroupRequest
        ],
    ) -> StoredDurableCompactionGroup:
        stored = self._require_group(
            group_id
        )
        group = stored.group
        if (
            _PHASE_ORDER[group.phase]
            < _PHASE_ORDER[
                DurableCompactionGroupPhase.AUTHORIZED
            ]
        ):
            raise DurableCompactionGroupError(
                "group must be authorized before preparation"
            )
        if (
            group.phase
            is DurableCompactionGroupPhase.COMPLETE
        ):
            return stored
        request_map = self._require_requests(
            group,
            requests,
        )

        # Freeze every member manifest before any group execution may start.
        for member in group.members:
            request = request_map[
                member.chain_id
            ]
            request.operator.prepare(
                member.workflow_id,
                request.retention,
                request.chain,
            )
        synced = self._sync_members(
            group,
            request_map,
        )
        if not all(
            member.prepared
            for member in synced
        ):
            raise DurableCompactionGroupError(
                "not every group member has a frozen pruning manifest"
            )
        return self._replace(
            group,
            phase=(
                DurableCompactionGroupPhase.PREPARED
            ),
            members=synced,
            next_member_index=0,
        )

    def _execute_from(
        self,
        group: DurableCompactionGroup,
        request_map: Mapping[
            str,
            DurableCompactionGroupRequest,
        ],
        *,
        start_index: int,
    ) -> StoredDurableCompactionGroup:
        current = group
        synced = self._sync_members(
            current,
            request_map,
        )
        current = self._replace(
            current,
            phase=(
                DurableCompactionGroupPhase.EXECUTING
            ),
            members=synced,
            next_member_index=start_index,
            completed_members=sum(
                1 for item in synced
                if item.complete
            ),
        ).group

        for index in range(
            start_index,
            len(current.members),
        ):
            member = current.members[
                index
            ]
            request = request_map[
                member.chain_id
            ]
            try:
                workflow = (
                    request.operator.current(
                        member.workflow_id
                    )
                )
                if workflow is None:
                    raise DurableCompactionGroupManualReview(
                        "member workflow disappeared during group execution"
                    )
                if workflow.workflow.complete:
                    result = request.operator.resume(
                        member.workflow_id,
                        request.retention,
                        request.chain,
                    )
                elif workflow.workflow.phase in {
                    DurableCompactionWorkflowPhase.EXECUTING,
                }:
                    result = request.operator.resume(
                        member.workflow_id,
                        request.retention,
                        request.chain,
                    )
                else:
                    result = request.operator.execute(
                        member.workflow_id,
                        request.retention,
                        request.chain,
                    )
                if not isinstance(
                    result,
                    DurableCompactionExecution,
                ) or not result.ok:
                    raise DurableCompactionGroupError(
                        "member pruning did not complete successfully"
                    )
            except (
                DurableCompactionWorkflowManualReview,
                DurableCompactionGroupManualReview,
            ) as exc:
                synced = self._sync_members(
                    current,
                    request_map,
                )
                current = self._replace(
                    current,
                    members=synced,
                    completed_members=sum(
                        1 for item in synced
                        if item.complete
                    ),
                    next_member_index=index,
                ).group
                self._note_error(
                    current,
                    exc,
                    manual_review=True,
                )
                raise DurableCompactionGroupManualReview(
                    str(exc)
                ) from exc
            except Exception as exc:
                synced = self._sync_members(
                    current,
                    request_map,
                )
                committed = sum(
                    1
                    for item in synced
                    if item.floor_committed
                    or item.complete
                )
                partial = (
                    0
                    < committed
                    < len(synced)
                )
                current = self._replace(
                    current,
                    members=synced,
                    completed_members=sum(
                        1 for item in synced
                        if item.complete
                    ),
                    next_member_index=index,
                ).group
                self._note_error(
                    current,
                    exc,
                    manual_review=False,
                    partial_commit=partial,
                )
                raise

            synced = self._sync_members(
                current,
                request_map,
            )
            current = self._replace(
                current,
                members=synced,
                completed_members=sum(
                    1 for item in synced
                    if item.complete
                ),
                next_member_index=index + 1,
                phase=(
                    DurableCompactionGroupPhase.PARTIAL_COMMIT
                    if (
                        index + 1
                        < len(synced)
                        and any(
                            item.floor_committed
                            or item.complete
                            for item in synced
                        )
                    )
                    else DurableCompactionGroupPhase.EXECUTING
                ),
            ).group

        synced = self._sync_members(
            current,
            request_map,
        )
        if not all(
            member.complete
            for member in synced
        ):
            raise DurableCompactionGroupError(
                "group execution ended before every member completed"
            )
        return self._replace(
            current,
            phase=(
                DurableCompactionGroupPhase.COMPLETE
            ),
            members=synced,
            next_member_index=len(synced),
            completed_members=len(synced),
        )

    def execute(
        self,
        group_id: str,
        requests: Sequence[
            DurableCompactionGroupRequest
        ],
    ) -> StoredDurableCompactionGroup:
        stored = self._require_group(
            group_id
        )
        group = stored.group
        if (
            group.phase
            is not DurableCompactionGroupPhase.PREPARED
        ):
            if group.phase in {
                DurableCompactionGroupPhase.EXECUTING,
                DurableCompactionGroupPhase.PARTIAL_COMMIT,
            }:
                return self.resume(
                    group_id,
                    requests,
                )
            if group.complete:
                return stored
            raise DurableCompactionGroupError(
                "group must be fully prepared before execution"
            )
        request_map = self._require_requests(
            group,
            requests,
        )
        return self._execute_from(
            group,
            request_map,
            start_index=0,
        )

    def resume(
        self,
        group_id: str,
        requests: Sequence[
            DurableCompactionGroupRequest
        ],
    ) -> StoredDurableCompactionGroup:
        stored = self._require_group(
            group_id
        )
        group = stored.group
        if group.complete:
            return stored
        if group.phase not in {
            DurableCompactionGroupPhase.EXECUTING,
            DurableCompactionGroupPhase.PARTIAL_COMMIT,
        }:
            raise DurableCompactionGroupError(
                "group is not in a resumable execution phase"
            )
        request_map = self._require_requests(
            group,
            requests,
        )
        synced = self._sync_members(
            group,
            request_map,
        )
        if any(
            member.manual_review
            for member in synced
        ):
            self._replace(
                group,
                phase=(
                    DurableCompactionGroupPhase.MANUAL_REVIEW
                ),
                members=synced,
                completed_members=sum(
                    1 for item in synced
                    if item.complete
                ),
            )
            raise DurableCompactionGroupManualReview(
                "member workflow requires manual review"
            )

        start_index = 0
        for index, member in enumerate(
            synced
        ):
            if not member.complete:
                start_index = index
                break
        else:
            return self._replace(
                group,
                phase=(
                    DurableCompactionGroupPhase.COMPLETE
                ),
                members=synced,
                next_member_index=len(synced),
                completed_members=len(synced),
            )

        updated = self._replace(
            group,
            phase=(
                DurableCompactionGroupPhase.PARTIAL_COMMIT
                if any(
                    item.floor_committed
                    or item.complete
                    for item in synced
                )
                else DurableCompactionGroupPhase.EXECUTING
            ),
            members=synced,
            next_member_index=start_index,
            completed_members=sum(
                1 for item in synced
                if item.complete
            ),
        ).group
        return self._execute_from(
            updated,
            request_map,
            start_index=start_index,
        )

    def inspect(
        self,
        group_id: str,
        requests: Sequence[
            DurableCompactionGroupRequest
        ],
    ) -> DurableCompactionGroupInspection:
        stored = self.current(
            group_id
        )
        if stored is None:
            raise DurableCompactionGroupError(
                "compaction group is missing"
            )
        group = stored.group
        request_map = self._require_requests(
            group,
            requests,
        )
        reasons: list[str] = []
        current_values: list[
            tuple[str, bool]
        ] = []
        floor_values: list[
            tuple[str, bool]
        ] = []

        for member in group.members:
            request = request_map[
                member.chain_id
            ]
            try:
                report = request.operator.inspect(
                    member.workflow_id,
                    request.retention,
                    request.chain,
                )
                current_values.append(
                    (
                        member.chain_id,
                        report.current,
                    )
                )
                if not report.current:
                    reasons.extend(
                        f"{member.chain_id}: {reason}"
                        for reason in report.reasons
                    )
                workflow = report.stored.workflow
                floor_values.append(
                    (
                        member.chain_id,
                        bool(
                            workflow.floor_id
                            or workflow.complete
                        ),
                    )
                )
                if (
                    workflow.binding_digest
                    != member.workflow_binding_digest
                ):
                    reasons.append(
                        f"{member.chain_id}: workflow binding changed"
                    )
            except Exception as exc:
                current_values.append(
                    (
                        member.chain_id,
                        False,
                    )
                )
                floor_values.append(
                    (
                        member.chain_id,
                        member.floor_committed,
                    )
                )
                reasons.append(
                    f"{member.chain_id}: inspection failed: "
                    f"{type(exc).__name__}"
                )

        return DurableCompactionGroupInspection(
            stored,
            tuple(current_values),
            tuple(floor_values),
            tuple(dict.fromkeys(reasons)),
        )
