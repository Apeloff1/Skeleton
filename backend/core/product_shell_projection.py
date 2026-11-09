"""Read-only P1 product/workspace projection over durable operation authority.

The product shell may display progress, blockers, cost, evidence and terminal
result metadata, but it never owns operation lifecycle state. Canonical state
comes from StoredOperation + the accepted PROD-02 OperationProjectionState.
Supplemental fields may only be derived from stream events whose exact content
digest appears in the accepted projection receipt window.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable, Mapping

from core.operation_projection import (
    OperationProjectionState,
    verify_projection_authority,
)
from skeleton.contracts.canonical import EvidenceRef
from skeleton.contracts.operation import OperationState
from skeleton.frontier.contracts import stable_content_digest
from skeleton.frontier.operation_stream import StreamEvent
from skeleton.persistence.operation_store import StoredOperation


PRODUCT_PROJECTION_SCHEMA_VERSION = 1
PRODUCT_PROJECTION_TASK_ID = "P1-PROD-03"
PRODUCT_PROJECTION_ACCOUNTABILITY_ID = "ACC-P1-PROD-03"
_MAX_BLOCKERS = 32
_MAX_EVIDENCE = 64
_MAX_LABEL = 256
_STATE_PROGRESS = {
    OperationState.CREATED: 0.05,
    OperationState.VALIDATED: 0.15,
    OperationState.AUTHORIZED: 0.25,
    OperationState.ADMITTED: 0.35,
    OperationState.QUEUED: 0.45,
    OperationState.RUNNING: 0.60,
    OperationState.WAITING_FOR_TOOL: 0.65,
    OperationState.WAITING_FOR_USER: 0.65,
    OperationState.RETRYING: 0.55,
    OperationState.DEGRADED: 0.50,
    OperationState.COMPLETED: 1.0,
    OperationState.FAILED: 1.0,
    OperationState.CANCELLED: 1.0,
}
_STATE_BLOCKERS = {
    OperationState.WAITING_FOR_TOOL: (
        "state:waiting-for-tool",
        "Waiting for a canonical tool result.",
    ),
    OperationState.WAITING_FOR_USER: (
        "state:waiting-for-user",
        "Waiting for user input.",
    ),
    OperationState.RETRYING: (
        "state:retrying",
        "Retry policy is active.",
    ),
    OperationState.DEGRADED: (
        "state:degraded",
        "Operation is running in degraded mode.",
    ),
}


class ProductProjectionError(ValueError):
    """Workspace/product projection cannot be derived safely."""


def _text(value: object, field: str, *, maximum: int = _MAX_LABEL) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProductProjectionError(f"{field} must be non-empty")
    normalized = value.strip()
    if normalized != value or len(normalized) > maximum:
        raise ProductProjectionError(f"{field} must be normalized")
    return normalized


def _sha256(value: object, field: str) -> str:
    text = _text(value, field, maximum=64)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ProductProjectionError(f"{field} must be lowercase sha256")
    return text


def _finite_nonnegative(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProductProjectionError(f"{field} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ProductProjectionError(f"{field} must be finite and non-negative")
    return number


def _fraction(value: object, field: str) -> float:
    number = _finite_nonnegative(value, field)
    if number > 1.0:
        raise ProductProjectionError(f"{field} must be within [0, 1]")
    return number


@dataclass(frozen=True, slots=True)
class WorkspaceBlocker:
    blocker_id: str
    summary: str
    evidence_digest: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "blocker_id",
            _text(self.blocker_id, "blocker_id", maximum=128),
        )
        object.__setattr__(self, "summary", _text(self.summary, "summary"))
        if self.evidence_digest is not None:
            object.__setattr__(
                self,
                "evidence_digest",
                _sha256(self.evidence_digest, "evidence_digest"),
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "blocker_id": self.blocker_id,
            "summary": self.summary,
            "evidence_digest": self.evidence_digest,
        }


@dataclass(frozen=True, slots=True)
class WorkspaceCost:
    currency: str
    spent: float
    budget: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "currency",
            _text(self.currency, "currency", maximum=16).upper(),
        )
        object.__setattr__(self, "spent", _finite_nonnegative(self.spent, "spent"))
        if self.budget is not None:
            object.__setattr__(
                self,
                "budget",
                _finite_nonnegative(self.budget, "budget"),
            )
            if self.spent > self.budget:
                raise ProductProjectionError("spent cannot exceed budget")

    def as_dict(self) -> dict[str, Any]:
        return {
            "currency": self.currency,
            "spent": self.spent,
            "budget": self.budget,
        }


@dataclass(frozen=True, slots=True)
class WorkspaceTerminalResult:
    status: str
    result_ref: str | None
    message_id: str | None
    failure_code: str | None
    final_output_digest: str | None

    def __post_init__(self) -> None:
        if self.status not in {"completed", "failed", "cancelled"}:
            raise ProductProjectionError("invalid terminal result status")
        for field in ("result_ref", "message_id", "failure_code"):
            value = getattr(self, field)
            if value is not None:
                object.__setattr__(
                    self,
                    field,
                    _text(value, field, maximum=512),
                )
        if self.final_output_digest is not None:
            object.__setattr__(
                self,
                "final_output_digest",
                _sha256(self.final_output_digest, "final_output_digest"),
            )
        if self.status != "completed" and self.final_output_digest is not None:
            raise ProductProjectionError(
                "non-completed result cannot expose final output digest"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "result_ref": self.result_ref,
            "message_id": self.message_id,
            "failure_code": self.failure_code,
            "final_output_digest": self.final_output_digest,
        }


@dataclass(frozen=True, slots=True)
class WorkspaceProductProjection:
    operation_id: str
    tenant_id: str
    operation_state: str
    operation_version: int
    cursor_sequence: int
    progress: float
    progress_label: str
    blockers: tuple[WorkspaceBlocker, ...]
    cost: WorkspaceCost | None
    evidence: tuple[EvidenceRef, ...]
    terminal_result: WorkspaceTerminalResult | None
    authority_digest: str
    writable: bool = False
    task_id: str = PRODUCT_PROJECTION_TASK_ID
    accountability_id: str = PRODUCT_PROJECTION_ACCOUNTABILITY_ID
    schema_version: int = PRODUCT_PROJECTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "operation_id", _text(self.operation_id, "operation_id", maximum=64)
        )
        object.__setattr__(self, "tenant_id", _text(self.tenant_id, "tenant_id"))
        object.__setattr__(
            self,
            "operation_state",
            _text(self.operation_state, "operation_state", maximum=64),
        )
        if isinstance(self.operation_version, bool) or not isinstance(
            self.operation_version, int
        ) or self.operation_version < 1:
            raise ProductProjectionError("operation_version must be positive")
        if isinstance(self.cursor_sequence, bool) or not isinstance(
            self.cursor_sequence, int
        ) or self.cursor_sequence < 0:
            raise ProductProjectionError("cursor_sequence must be non-negative")
        object.__setattr__(self, "progress", _fraction(self.progress, "progress"))
        object.__setattr__(
            self,
            "progress_label",
            _text(self.progress_label, "progress_label"),
        )
        if not isinstance(self.blockers, tuple) or any(
            not isinstance(item, WorkspaceBlocker) for item in self.blockers
        ):
            raise ProductProjectionError("blockers must contain WorkspaceBlocker")
        if len(self.blockers) > _MAX_BLOCKERS:
            raise ProductProjectionError("blocker limit exceeded")
        if self.cost is not None and not isinstance(self.cost, WorkspaceCost):
            raise ProductProjectionError("cost must be WorkspaceCost")
        if not isinstance(self.evidence, tuple) or any(
            not isinstance(item, EvidenceRef) for item in self.evidence
        ):
            raise ProductProjectionError("evidence must contain EvidenceRef")
        if len(self.evidence) > _MAX_EVIDENCE:
            raise ProductProjectionError("evidence limit exceeded")
        if self.terminal_result is not None and not isinstance(
            self.terminal_result, WorkspaceTerminalResult
        ):
            raise ProductProjectionError(
                "terminal_result must be WorkspaceTerminalResult"
            )
        object.__setattr__(
            self,
            "authority_digest",
            _sha256(self.authority_digest, "authority_digest"),
        )
        if self.writable is not False:
            raise ProductProjectionError("product projection is read-only")
        if self.task_id != PRODUCT_PROJECTION_TASK_ID:
            raise ProductProjectionError("task_id drift")
        if self.accountability_id != PRODUCT_PROJECTION_ACCOUNTABILITY_ID:
            raise ProductProjectionError("accountability_id drift")
        if self.schema_version != PRODUCT_PROJECTION_SCHEMA_VERSION:
            raise ProductProjectionError("unsupported projection schema")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "operation_id": self.operation_id,
            "tenant_id": self.tenant_id,
            "operation_state": self.operation_state,
            "operation_version": self.operation_version,
            "cursor_sequence": self.cursor_sequence,
            "progress": self.progress,
            "progress_label": self.progress_label,
            "blockers": [item.as_dict() for item in self.blockers],
            "cost": None if self.cost is None else self.cost.as_dict(),
            "evidence": [
                {
                    "source": item.source,
                    "digest": item.digest,
                    "category": item.category,
                }
                for item in self.evidence
            ],
            "terminal_result": (
                None if self.terminal_result is None else self.terminal_result.as_dict()
            ),
            "authority_digest": self.authority_digest,
            "writable": False,
        }

    @property
    def projection_digest(self) -> str:
        return stable_content_digest(self.as_dict())

    def evidence_ref(self) -> EvidenceRef:
        return EvidenceRef(
            source=f"p1:prod-03:workspace:{self.operation_id}",
            digest=self.projection_digest,
            category="workspace_product_projection",
        )


def _receipt_map(
    projection: OperationProjectionState,
) -> dict[int, tuple[str, str]]:
    return {
        item.sequence: (item.event_id, item.event_digest)
        for item in projection.recent_events
    }


def _verified_events(
    projection: OperationProjectionState,
    events: Iterable[StreamEvent],
) -> tuple[StreamEvent, ...]:
    receipts = _receipt_map(projection)
    rows = tuple(events)
    seen_sequences: set[int] = set()
    for event in rows:
        if not isinstance(event, StreamEvent):
            raise ProductProjectionError("events must contain StreamEvent")
        if event.operation_id != projection.operation_id:
            raise ProductProjectionError("event belongs to a different operation")
        if event.sequence > projection.cursor_sequence:
            raise ProductProjectionError("event is ahead of accepted projection cursor")
        if event.sequence in seen_sequences:
            raise ProductProjectionError("duplicate event sequence")
        seen_sequences.add(event.sequence)
        receipt = receipts.get(event.sequence)
        if receipt is None:
            raise ProductProjectionError(
                "event is outside exact accepted receipt window"
            )
        digest = stable_content_digest(event.as_dict())
        if receipt != (event.event_id, digest):
            raise ProductProjectionError("event receipt digest mismatch")
    return tuple(sorted(rows, key=lambda item: item.sequence))


def _supplemental_progress(
    state: OperationState,
    events: tuple[StreamEvent, ...],
) -> tuple[float, str]:
    progress = _STATE_PROGRESS[state]
    label = state.value.replace("_", " ")
    for event in events:
        if "progress" not in event.payload:
            continue
        candidate = _fraction(event.payload["progress"], "event.progress")
        candidate_label = event.payload.get("progress_label")
        if candidate_label is not None:
            label = _text(candidate_label, "event.progress_label")
        progress = candidate
    if state in {
        OperationState.COMPLETED,
        OperationState.FAILED,
        OperationState.CANCELLED,
    }:
        progress = 1.0
    return progress, label


def _supplemental_blockers(
    state: OperationState,
    events: tuple[StreamEvent, ...],
) -> tuple[WorkspaceBlocker, ...]:
    active: dict[str, WorkspaceBlocker] = {}
    derived = _STATE_BLOCKERS.get(state)
    if derived is not None:
        blocker_id, summary = derived
        active[blocker_id] = WorkspaceBlocker(blocker_id, summary)

    for event in events:
        rows = event.payload.get("blockers")
        if rows is None:
            continue
        if not isinstance(rows, list):
            raise ProductProjectionError("event.blockers must be a list")
        for row in rows:
            if not isinstance(row, Mapping):
                raise ProductProjectionError("blocker entry must be an object")
            blocker_id = _text(row.get("blocker_id"), "blocker_id", maximum=128)
            enabled = row.get("active", True)
            if not isinstance(enabled, bool):
                raise ProductProjectionError("blocker active flag must be boolean")
            if not enabled:
                active.pop(blocker_id, None)
                continue
            active[blocker_id] = WorkspaceBlocker(
                blocker_id=blocker_id,
                summary=_text(row.get("summary"), "blocker summary"),
                evidence_digest=(
                    None
                    if row.get("evidence_digest") is None
                    else _sha256(row.get("evidence_digest"), "blocker evidence_digest")
                ),
            )
            if len(active) > _MAX_BLOCKERS:
                raise ProductProjectionError("blocker limit exceeded")
    return tuple(active[key] for key in sorted(active))


def _supplemental_cost(
    events: tuple[StreamEvent, ...],
) -> WorkspaceCost | None:
    current: WorkspaceCost | None = None
    for event in events:
        row = event.payload.get("cost")
        if row is None:
            continue
        if not isinstance(row, Mapping):
            raise ProductProjectionError("event.cost must be an object")
        candidate = WorkspaceCost(
            currency=_text(row.get("currency"), "cost.currency", maximum=16),
            spent=_finite_nonnegative(row.get("spent"), "cost.spent"),
            budget=(
                None
                if row.get("budget") is None
                else _finite_nonnegative(row.get("budget"), "cost.budget")
            ),
        )
        if current is not None:
            if candidate.currency != current.currency:
                raise ProductProjectionError("cost currency cannot change")
            if candidate.spent < current.spent:
                raise ProductProjectionError("cost spent cannot decrease")
            if (
                current.budget is not None
                and candidate.budget is not None
                and candidate.budget != current.budget
            ):
                raise ProductProjectionError("cost budget cannot change")
        current = candidate
    return current


def _supplemental_evidence(
    events: tuple[StreamEvent, ...],
) -> tuple[EvidenceRef, ...]:
    by_key: dict[tuple[str, str, str], EvidenceRef] = {}
    for event in events:
        rows = event.payload.get("evidence")
        if rows is None:
            continue
        if not isinstance(rows, list):
            raise ProductProjectionError("event.evidence must be a list")
        for row in rows:
            if not isinstance(row, Mapping):
                raise ProductProjectionError("evidence entry must be an object")
            item = EvidenceRef(
                source=_text(row.get("source"), "evidence.source", maximum=2048),
                digest=_sha256(row.get("digest"), "evidence.digest"),
                category=_text(row.get("category"), "evidence.category", maximum=128),
            )
            by_key[(item.source, item.digest, item.category)] = item
            if len(by_key) > _MAX_EVIDENCE:
                raise ProductProjectionError("evidence limit exceeded")
    return tuple(by_key[key] for key in sorted(by_key))


def _terminal_result(
    state: OperationState,
    events: tuple[StreamEvent, ...],
) -> WorkspaceTerminalResult | None:
    if state not in {
        OperationState.COMPLETED,
        OperationState.FAILED,
        OperationState.CANCELLED,
    }:
        return None
    status = state.value
    source: Mapping[str, Any] = {}
    for event in events:
        if event.type == f"operation.{status}" or event.type == "terminal":
            nested = event.payload.get("result")
            source = nested if isinstance(nested, Mapping) else event.payload
    final_output = source.get("final_output")
    if final_output is not None and not isinstance(final_output, str):
        raise ProductProjectionError("final_output must be text or null")
    digest = (
        stable_content_digest(final_output)
        if state is OperationState.COMPLETED and isinstance(final_output, str)
        else None
    )
    return WorkspaceTerminalResult(
        status=status,
        result_ref=source.get("result_ref") if isinstance(source.get("result_ref"), str) else None,
        message_id=source.get("message_id") if isinstance(source.get("message_id"), str) else None,
        failure_code=(
            source.get("failure_code")
            if isinstance(source.get("failure_code"), str)
            else None
        ),
        final_output_digest=digest,
    )


def project_workspace_product_state(
    *,
    authority: StoredOperation,
    projection: OperationProjectionState,
    events: Iterable[StreamEvent] = (),
) -> WorkspaceProductProjection:
    """Build a read-only product projection from exact durable authority."""

    if not isinstance(authority, StoredOperation):
        raise TypeError("authority must be StoredOperation")
    if not isinstance(projection, OperationProjectionState):
        raise TypeError("projection must be OperationProjectionState")

    authority_decision = verify_projection_authority(projection, authority)
    if not authority_decision.accepted:
        raise ProductProjectionError(
            "operation projection does not match durable authority: "
            + ",".join(authority_decision.reasons)
        )

    verified_events = _verified_events(projection, events)
    state = OperationState(authority.envelope.state)
    progress, progress_label = _supplemental_progress(state, verified_events)
    blockers = _supplemental_blockers(state, verified_events)
    cost = _supplemental_cost(verified_events)
    evidence = _supplemental_evidence(verified_events)
    terminal_result = _terminal_result(state, verified_events)

    return WorkspaceProductProjection(
        operation_id=authority.envelope.operation_id,
        tenant_id=authority.envelope.tenant_id,
        operation_state=state.value,
        operation_version=authority.version,
        cursor_sequence=projection.cursor_sequence,
        progress=progress,
        progress_label=progress_label,
        blockers=blockers,
        cost=cost,
        evidence=evidence,
        terminal_result=terminal_result,
        authority_digest=stable_content_digest(authority.as_dict()),
    )


__all__ = [
    "PRODUCT_PROJECTION_ACCOUNTABILITY_ID",
    "PRODUCT_PROJECTION_SCHEMA_VERSION",
    "PRODUCT_PROJECTION_TASK_ID",
    "ProductProjectionError",
    "WorkspaceBlocker",
    "WorkspaceCost",
    "WorkspaceProductProjection",
    "WorkspaceTerminalResult",
    "project_workspace_product_state",
]
