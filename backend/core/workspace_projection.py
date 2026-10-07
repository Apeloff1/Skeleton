"""P1 workspace/product projection contract.

This module is presentation-only. Canonical operation state is supplied by the
already verified PROD-02 OperationProjectionState and cannot be overridden by
workspace/UI callers. Progress, blockers, cost, evidence, and terminal results
are provenance-bound auxiliary records for product rendering.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Any, Iterable

from core.operation_projection import (
    OperationProjectionState,
    ProjectionAuthorityDecision,
)
from skeleton.contracts.canonical import EvidenceRef
from skeleton.contracts.operation import OperationState
from skeleton.frontier.contracts import stable_content_digest


WORKSPACE_PROJECTION_SCHEMA_VERSION = 1
WORKSPACE_PROJECTION_TASK_ID = "P1-PROD-03"
WORKSPACE_PROJECTION_ACCOUNTABILITY_ID = "ACC-P1-PROD-03"


class WorkspaceProjectionError(ValueError):
    """Workspace projection data violates canonical projection boundaries."""


class BlockerSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"


def _text(value: object, field: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkspaceProjectionError(f"{field} must be non-empty")
    normalized = value.strip()
    if normalized != value or len(normalized) > maximum:
        raise WorkspaceProjectionError(f"{field} must be normalized")
    return normalized


def _token(value: object, field: str, *, maximum: int = 192) -> str:
    text = _text(value, field, maximum=maximum)
    allowed = (
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "abcdefghijklmnopqrstuvwxyz"
        "0123456789._:/-"
    )
    if any(char not in allowed for char in text):
        raise WorkspaceProjectionError(f"{field} must be a canonical token")
    return text


def _sha256(value: object, field: str) -> str:
    text = _text(value, field, maximum=64)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise WorkspaceProjectionError(f"{field} must be lowercase sha256")
    return text


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise WorkspaceProjectionError(
            f"{field} must be a non-negative integer"
        )
    return value


def _positive_int(value: object, field: str) -> int:
    value = _nonnegative_int(value, field)
    if value < 1:
        raise WorkspaceProjectionError(f"{field} must be positive")
    return value


def _nonnegative_float(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WorkspaceProjectionError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise WorkspaceProjectionError(
            f"{field} must be finite and non-negative"
        )
    return result


def _evidence_ref(value: object, field: str) -> EvidenceRef:
    if not isinstance(value, EvidenceRef):
        raise WorkspaceProjectionError(f"{field} must be EvidenceRef")
    _text(value.source, f"{field}.source")
    _sha256(value.digest, f"{field}.digest")
    _token(value.category, f"{field}.category", maximum=128)
    return value


def _evidence_payload(value: EvidenceRef) -> dict[str, str]:
    return {
        "source": value.source,
        "digest": value.digest,
        "category": value.category,
    }


@dataclass(frozen=True, slots=True)
class ProgressProjection:
    completed_units: int
    total_units: int
    label: str
    evidence: EvidenceRef

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "completed_units",
            _nonnegative_int(self.completed_units, "completed_units"),
        )
        object.__setattr__(
            self,
            "total_units",
            _positive_int(self.total_units, "total_units"),
        )
        if self.completed_units > self.total_units:
            raise WorkspaceProjectionError(
                "completed_units cannot exceed total_units"
            )
        object.__setattr__(self, "label", _text(self.label, "label", maximum=512))
        object.__setattr__(
            self,
            "evidence",
            _evidence_ref(self.evidence, "progress evidence"),
        )

    @property
    def fraction(self) -> float:
        return self.completed_units / self.total_units

    def payload(self) -> dict[str, Any]:
        return {
            "completed_units": self.completed_units,
            "total_units": self.total_units,
            "fraction": self.fraction,
            "label": self.label,
            "evidence": _evidence_payload(self.evidence),
        }


@dataclass(frozen=True, slots=True)
class BlockerProjection:
    blocker_id: str
    summary: str
    severity: BlockerSeverity
    evidence: EvidenceRef

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "blocker_id",
            _token(self.blocker_id, "blocker_id"),
        )
        object.__setattr__(
            self,
            "summary",
            _text(self.summary, "summary", maximum=1024),
        )
        try:
            object.__setattr__(self, "severity", BlockerSeverity(self.severity))
        except ValueError as exc:
            raise WorkspaceProjectionError("invalid blocker severity") from exc
        object.__setattr__(
            self,
            "evidence",
            _evidence_ref(self.evidence, "blocker evidence"),
        )

    def payload(self) -> dict[str, Any]:
        return {
            "blocker_id": self.blocker_id,
            "summary": self.summary,
            "severity": self.severity.value,
            "evidence": _evidence_payload(self.evidence),
        }


@dataclass(frozen=True, slots=True)
class CostProjection:
    spent_units: float
    remaining_units: float | None
    unit: str
    evidence: EvidenceRef

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "spent_units",
            _nonnegative_float(self.spent_units, "spent_units"),
        )
        if self.remaining_units is not None:
            object.__setattr__(
                self,
                "remaining_units",
                _nonnegative_float(
                    self.remaining_units,
                    "remaining_units",
                ),
            )
        object.__setattr__(self, "unit", _token(self.unit, "unit", maximum=64))
        object.__setattr__(
            self,
            "evidence",
            _evidence_ref(self.evidence, "cost evidence"),
        )

    def payload(self) -> dict[str, Any]:
        return {
            "spent_units": self.spent_units,
            "remaining_units": self.remaining_units,
            "unit": self.unit,
            "evidence": _evidence_payload(self.evidence),
        }


@dataclass(frozen=True, slots=True)
class TerminalResultProjection:
    summary: str
    result: EvidenceRef

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "summary",
            _text(self.summary, "terminal summary", maximum=2048),
        )
        object.__setattr__(
            self,
            "result",
            _evidence_ref(self.result, "terminal result"),
        )

    def payload(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "result": _evidence_payload(self.result),
        }


def _normalize_evidence(
    values: Iterable[EvidenceRef],
) -> tuple[EvidenceRef, ...]:
    if isinstance(values, (str, bytes)):
        raise WorkspaceProjectionError(
            "evidence must contain EvidenceRef values"
        )
    by_key: dict[tuple[str, str, str], EvidenceRef] = {}
    for item in values:
        row = _evidence_ref(item, "evidence")
        by_key[(row.source, row.digest, row.category)] = row
    return tuple(by_key[key] for key in sorted(by_key))


@dataclass(frozen=True, slots=True)
class WorkspaceProjection:
    operation_id: str
    tenant_id: str
    trace_id: str
    canonical_state: OperationState
    operation_version: int
    cursor_sequence: int
    terminal: bool
    operation_projection_digest: str
    projection_authority_digest: str
    progress: ProgressProjection | None = None
    blockers: tuple[BlockerProjection, ...] = ()
    cost: CostProjection | None = None
    evidence: tuple[EvidenceRef, ...] = ()
    terminal_result: TerminalResultProjection | None = None
    schema_version: int = WORKSPACE_PROJECTION_SCHEMA_VERSION
    task_id: str = WORKSPACE_PROJECTION_TASK_ID
    accountability_id: str = WORKSPACE_PROJECTION_ACCOUNTABILITY_ID

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "operation_id",
            _text(self.operation_id, "operation_id", maximum=64),
        )
        object.__setattr__(self, "tenant_id", _text(self.tenant_id, "tenant_id"))
        object.__setattr__(
            self,
            "trace_id",
            _text(self.trace_id, "trace_id", maximum=256),
        )
        try:
            state = OperationState(self.canonical_state)
        except ValueError as exc:
            raise WorkspaceProjectionError("invalid canonical_state") from exc
        object.__setattr__(self, "canonical_state", state)
        object.__setattr__(
            self,
            "operation_version",
            _positive_int(self.operation_version, "operation_version"),
        )
        object.__setattr__(
            self,
            "cursor_sequence",
            _positive_int(self.cursor_sequence, "cursor_sequence"),
        )
        if not isinstance(self.terminal, bool):
            raise WorkspaceProjectionError("terminal must be boolean")
        object.__setattr__(
            self,
            "operation_projection_digest",
            _sha256(
                self.operation_projection_digest,
                "operation_projection_digest",
            ),
        )
        object.__setattr__(
            self,
            "projection_authority_digest",
            _sha256(
                self.projection_authority_digest,
                "projection_authority_digest",
            ),
        )
        if self.progress is not None and not isinstance(
            self.progress, ProgressProjection
        ):
            raise WorkspaceProjectionError(
                "progress must be ProgressProjection"
            )
        if not isinstance(self.blockers, tuple) or any(
            not isinstance(item, BlockerProjection) for item in self.blockers
        ):
            raise WorkspaceProjectionError(
                "blockers must contain BlockerProjection"
            )
        blocker_ids = [item.blocker_id for item in self.blockers]
        if len(blocker_ids) != len(set(blocker_ids)):
            raise WorkspaceProjectionError("blocker IDs must be unique")
        if self.cost is not None and not isinstance(self.cost, CostProjection):
            raise WorkspaceProjectionError("cost must be CostProjection")
        object.__setattr__(
            self,
            "evidence",
            _normalize_evidence(self.evidence),
        )
        if self.terminal_result is not None and not isinstance(
            self.terminal_result,
            TerminalResultProjection,
        ):
            raise WorkspaceProjectionError(
                "terminal_result must be TerminalResultProjection"
            )
        derived_terminal = self.canonical_state in {
            OperationState.COMPLETED,
            OperationState.FAILED,
            OperationState.CANCELLED,
        }
        if self.terminal != derived_terminal:
            raise WorkspaceProjectionError(
                "terminal flag must derive from canonical state"
            )
        if self.terminal and self.terminal_result is None:
            raise WorkspaceProjectionError(
                "terminal projection requires terminal_result"
            )
        if not self.terminal and self.terminal_result is not None:
            raise WorkspaceProjectionError(
                "non-terminal projection cannot include terminal_result"
            )
        if self.schema_version != WORKSPACE_PROJECTION_SCHEMA_VERSION:
            raise WorkspaceProjectionError(
                "unsupported workspace projection schema"
            )
        if self.task_id != WORKSPACE_PROJECTION_TASK_ID:
            raise WorkspaceProjectionError("task_id drift")
        if self.accountability_id != WORKSPACE_PROJECTION_ACCOUNTABILITY_ID:
            raise WorkspaceProjectionError("accountability_id drift")

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "operation_id": self.operation_id,
            "tenant_id": self.tenant_id,
            "trace_id": self.trace_id,
            "canonical_state": self.canonical_state.value,
            "operation_version": self.operation_version,
            "cursor_sequence": self.cursor_sequence,
            "terminal": self.terminal,
            "operation_projection_digest": self.operation_projection_digest,
            "projection_authority_digest": self.projection_authority_digest,
            "progress": None if self.progress is None else self.progress.payload(),
            "blockers": [
                item.payload()
                for item in sorted(self.blockers, key=lambda row: row.blocker_id)
            ],
            "cost": None if self.cost is None else self.cost.payload(),
            "evidence": [_evidence_payload(item) for item in self.evidence],
            "terminal_result": (
                None
                if self.terminal_result is None
                else self.terminal_result.payload()
            ),
            "canonical_authority": "durable-operation-projection",
            "production_authority": False,
        }

    @property
    def projection_digest(self) -> str:
        return stable_content_digest(self.payload())

@dataclass(frozen=True, slots=True)
class WorkspaceProjectionDecision:
    accepted: bool
    reasons: tuple[str, ...]
    workspace_projection_digest: str
    operation_projection_digest: str
    projection_authority_digest: str
    operation_id: str
    tenant_id: str
    operation_version: int
    cursor_sequence: int
    schema_version: int = WORKSPACE_PROJECTION_SCHEMA_VERSION
    task_id: str = WORKSPACE_PROJECTION_TASK_ID
    accountability_id: str = WORKSPACE_PROJECTION_ACCOUNTABILITY_ID

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise WorkspaceProjectionError("accepted must be boolean")
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item for item in self.reasons
        ):
            raise WorkspaceProjectionError(
                "reasons must contain non-empty strings"
            )
        for field in (
            "workspace_projection_digest",
            "operation_projection_digest",
            "projection_authority_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "operation_id",
            _text(self.operation_id, "operation_id", maximum=64),
        )
        object.__setattr__(self, "tenant_id", _text(self.tenant_id, "tenant_id"))
        object.__setattr__(
            self,
            "operation_version",
            _positive_int(self.operation_version, "operation_version"),
        )
        object.__setattr__(
            self,
            "cursor_sequence",
            _positive_int(self.cursor_sequence, "cursor_sequence"),
        )
        if self.schema_version != WORKSPACE_PROJECTION_SCHEMA_VERSION:
            raise WorkspaceProjectionError("unsupported decision schema")
        if self.task_id != WORKSPACE_PROJECTION_TASK_ID:
            raise WorkspaceProjectionError("task_id drift")
        if self.accountability_id != WORKSPACE_PROJECTION_ACCOUNTABILITY_ID:
            raise WorkspaceProjectionError("accountability_id drift")

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "workspace_projection_digest": self.workspace_projection_digest,
            "operation_projection_digest": self.operation_projection_digest,
            "projection_authority_digest": self.projection_authority_digest,
            "operation_id": self.operation_id,
            "tenant_id": self.tenant_id,
            "operation_version": self.operation_version,
            "cursor_sequence": self.cursor_sequence,
        }

    @property
    def decision_digest(self) -> str:
        return stable_content_digest(self.payload())

    def accepted_evidence_ref(self) -> EvidenceRef:
        if not self.accepted:
            raise WorkspaceProjectionError(
                "rejected workspace projection cannot become promotion evidence"
            )
        return EvidenceRef(
            source=f"p1:prod-03:workspace-decision:{self.operation_id}",
            digest=self.decision_digest,
            category="workspace_projection_authority",
        )


def build_workspace_projection(
    *,
    operation_projection: OperationProjectionState,
    authority: ProjectionAuthorityDecision,
    progress: ProgressProjection | None = None,
    blockers: Iterable[BlockerProjection] = (),
    cost: CostProjection | None = None,
    evidence: Iterable[EvidenceRef] = (),
    terminal_result: TerminalResultProjection | None = None,
) -> WorkspaceProjection:
    """Build a product view from verified operation truth only."""

    if not isinstance(operation_projection, OperationProjectionState):
        raise TypeError(
            "operation_projection must be OperationProjectionState"
        )
    if not isinstance(authority, ProjectionAuthorityDecision):
        raise TypeError("authority must be ProjectionAuthorityDecision")
    if not authority.accepted:
        raise WorkspaceProjectionError(
            "operation projection authority must be accepted"
        )
    if not operation_projection.initialized:
        raise WorkspaceProjectionError(
            "operation projection must be initialized"
        )
    if authority.operation_id != operation_projection.operation_id:
        raise WorkspaceProjectionError("operation identity mismatch")
    if authority.tenant_id != operation_projection.tenant_id:
        raise WorkspaceProjectionError("tenant identity mismatch")
    if (
        authority.projection_digest
        != operation_projection.projection_digest
    ):
        raise WorkspaceProjectionError(
            "operation projection digest mismatch"
        )
    if authority.operation_version != operation_projection.operation_version:
        raise WorkspaceProjectionError(
            "operation version mismatch"
        )
    if authority.cursor_sequence != operation_projection.cursor_sequence:
        raise WorkspaceProjectionError(
            "stream cursor mismatch"
        )

    blocker_rows = tuple(blockers)
    return WorkspaceProjection(
        operation_id=operation_projection.operation_id,
        tenant_id=operation_projection.tenant_id,
        trace_id=operation_projection.trace_id,
        canonical_state=operation_projection.state,
        operation_version=operation_projection.operation_version,
        cursor_sequence=operation_projection.cursor_sequence,
        terminal=operation_projection.terminal,
        operation_projection_digest=operation_projection.projection_digest,
        projection_authority_digest=authority.decision_digest,
        progress=progress,
        blockers=blocker_rows,
        cost=cost,
        evidence=tuple(evidence),
        terminal_result=terminal_result,
    )


def verify_workspace_projection(
    workspace: WorkspaceProjection,
    operation_projection: OperationProjectionState,
    authority: ProjectionAuthorityDecision,
) -> WorkspaceProjectionDecision:
    """Verify a cached/client workspace view still matches canonical projection."""

    if not isinstance(workspace, WorkspaceProjection):
        raise TypeError("workspace must be WorkspaceProjection")
    if not isinstance(operation_projection, OperationProjectionState):
        raise TypeError(
            "operation_projection must be OperationProjectionState"
        )
    if not isinstance(authority, ProjectionAuthorityDecision):
        raise TypeError("authority must be ProjectionAuthorityDecision")

    reasons: list[str] = []
    if not authority.accepted:
        reasons.append("operation-projection-authority-rejected")
    if workspace.operation_id != operation_projection.operation_id:
        reasons.append("operation-id-mismatch")
    if workspace.tenant_id != operation_projection.tenant_id:
        reasons.append("tenant-id-mismatch")
    if workspace.trace_id != operation_projection.trace_id:
        reasons.append("trace-id-mismatch")
    if workspace.canonical_state is not operation_projection.state:
        reasons.append("canonical-state-mismatch")
    if workspace.operation_version != operation_projection.operation_version:
        reasons.append("operation-version-mismatch")
    if workspace.cursor_sequence != operation_projection.cursor_sequence:
        reasons.append("cursor-sequence-mismatch")
    if workspace.terminal != operation_projection.terminal:
        reasons.append("terminal-state-mismatch")
    if (
        workspace.operation_projection_digest
        != operation_projection.projection_digest
    ):
        reasons.append("operation-projection-digest-mismatch")
    if workspace.projection_authority_digest != authority.decision_digest:
        reasons.append("projection-authority-digest-mismatch")
    if authority.projection_digest != operation_projection.projection_digest:
        reasons.append("authority-projection-digest-mismatch")

    normalized = tuple(sorted(set(reasons)))
    return WorkspaceProjectionDecision(
        accepted=not normalized,
        reasons=normalized,
        workspace_projection_digest=workspace.projection_digest,
        operation_projection_digest=operation_projection.projection_digest,
        projection_authority_digest=authority.decision_digest,
        operation_id=operation_projection.operation_id,
        tenant_id=operation_projection.tenant_id,
        operation_version=operation_projection.operation_version,
        cursor_sequence=operation_projection.cursor_sequence,
    )


__all__ = [
    "WORKSPACE_PROJECTION_ACCOUNTABILITY_ID",
    "WORKSPACE_PROJECTION_SCHEMA_VERSION",
    "WORKSPACE_PROJECTION_TASK_ID",
    "BlockerProjection",
    "BlockerSeverity",
    "CostProjection",
    "ProgressProjection",
    "TerminalResultProjection",
    "WorkspaceProjection",
    "WorkspaceProjectionDecision",
    "WorkspaceProjectionError",
    "build_workspace_projection",
    "verify_workspace_projection",
]
