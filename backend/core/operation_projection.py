"""Deterministic client projection authority for durable operation streams.

The durable OperationStore and OperationEventStore remain authoritative. This
module models the state a browser/desktop client may derive from replayed stream
events and proves that the derived projection converges to the durable operation
snapshot.

Safety properties:
- only contiguous stream sequences advance a projection;
- exact duplicate deliveries are idempotent;
- unknown/conflicting duplicates require resync or fail closed;
- event state/version/trace identity must match canonical operation semantics;
- illegal operation transitions cannot be projected;
- a projection is promotion evidence only after it matches durable authority.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Iterable

from skeleton.contracts.canonical import EvidenceRef
from skeleton.contracts.operation import (
    OperationEnvelope,
    OperationState,
    OperationTransitionError,
)
from skeleton.frontier.contracts import stable_content_digest
from skeleton.frontier.operation_stream import StreamEvent
from skeleton.persistence.operation_store import StoredOperation


PROJECTION_SCHEMA_VERSION = 1
PROJECTION_TASK_ID = "P1-PROD-02"
PROJECTION_ACCOUNTABILITY_ID = "ACC-P1-PROD-02"
MAX_EXACT_EVENT_RECEIPTS = 32


class OperationProjectionError(ValueError):
    """Projection input violates the canonical product-state contract."""


class ProjectionResyncRequired(OperationProjectionError):
    """The client cannot safely advance without an authoritative resync."""


class ProjectionConflictError(OperationProjectionError):
    """The stream contradicts already applied canonical projection history."""


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise OperationProjectionError(
            f"{field} must be a non-negative integer"
        )
    return value


def _positive_int(value: object, field: str) -> int:
    value = _nonnegative_int(value, field)
    if value < 1:
        raise OperationProjectionError(f"{field} must be positive")
    return value


def _text(value: object, field: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OperationProjectionError(f"{field} must be non-empty")
    normalized = value.strip()
    if normalized != value or len(normalized) > maximum:
        raise OperationProjectionError(f"{field} must be normalized")
    return normalized


@dataclass(frozen=True, slots=True)
class AppliedStreamReceipt:
    sequence: int
    event_id: str
    event_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "sequence",
            _positive_int(self.sequence, "sequence"),
        )
        object.__setattr__(
            self,
            "event_id",
            _text(self.event_id, "event_id", maximum=64),
        )
        digest = _text(
            self.event_digest,
            "event_digest",
            maximum=64,
        )
        if len(digest) != 64 or any(
            char not in "0123456789abcdef" for char in digest
        ):
            raise OperationProjectionError(
                "event_digest must be lowercase sha256"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "event_id": self.event_id,
            "event_digest": self.event_digest,
        }


@dataclass(frozen=True, slots=True)
class OperationProjectionState:
    envelope: OperationEnvelope
    operation_version: int
    cursor_sequence: int
    initialized: bool
    recent_events: tuple[AppliedStreamReceipt, ...] = ()
    source: str = "replay"
    schema_version: int = PROJECTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.envelope, OperationEnvelope):
            raise OperationProjectionError(
                "envelope must be OperationEnvelope"
            )
        object.__setattr__(
            self,
            "operation_version",
            _nonnegative_int(
                self.operation_version,
                "operation_version",
            ),
        )
        object.__setattr__(
            self,
            "cursor_sequence",
            _nonnegative_int(
                self.cursor_sequence,
                "cursor_sequence",
            ),
        )
        if not isinstance(self.initialized, bool):
            raise OperationProjectionError(
                "initialized must be boolean"
            )
        if not isinstance(self.recent_events, tuple) or any(
            not isinstance(item, AppliedStreamReceipt)
            for item in self.recent_events
        ):
            raise OperationProjectionError(
                "recent_events must contain AppliedStreamReceipt"
            )
        sequences = [item.sequence for item in self.recent_events]
        if sequences != sorted(sequences):
            raise OperationProjectionError(
                "recent_events must be sequence ordered"
            )
        if len(set(sequences)) != len(sequences):
            raise OperationProjectionError(
                "recent_events must have unique sequences"
            )
        if len(self.recent_events) > MAX_EXACT_EVENT_RECEIPTS:
            raise OperationProjectionError(
                "recent_events exceeds exact receipt window"
            )
        if self.recent_events and (
            self.recent_events[-1].sequence > self.cursor_sequence
        ):
            raise OperationProjectionError(
                "receipt sequence exceeds projection cursor"
            )
        object.__setattr__(
            self,
            "source",
            _text(self.source, "source", maximum=32),
        )
        if self.source not in {"replay", "resync"}:
            raise OperationProjectionError(
                "source must be replay or resync"
            )
        if self.schema_version != PROJECTION_SCHEMA_VERSION:
            raise OperationProjectionError(
                "unsupported projection schema version"
            )
        if not self.initialized and self.operation_version != 0:
            raise OperationProjectionError(
                "uninitialized projection must have operation_version=0"
            )

    @property
    def operation_id(self) -> str:
        return self.envelope.operation_id

    @property
    def tenant_id(self) -> str:
        return self.envelope.tenant_id

    @property
    def trace_id(self) -> str:
        return self.envelope.trace_id

    @property
    def state(self) -> OperationState:
        return OperationState(self.envelope.state)

    @property
    def terminal(self) -> bool:
        return self.initialized and self.envelope.terminal

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "operation_id": self.operation_id,
            "tenant_id": self.tenant_id,
            "trace_id": self.trace_id,
            "identity_digest": self.envelope.identity_digest,
            "state": self.state.value,
            "operation_version": self.operation_version,
            "cursor_sequence": self.cursor_sequence,
            "initialized": self.initialized,
            "terminal": self.terminal,
            "source": self.source,
            "recent_events": [
                item.payload() for item in self.recent_events
            ],
        }

    @property
    def projection_digest(self) -> str:
        return stable_content_digest(self.payload())


@dataclass(frozen=True, slots=True)
class ProjectionAuthorityDecision:
    accepted: bool
    reasons: tuple[str, ...]
    operation_id: str
    tenant_id: str
    projection_digest: str
    authority_digest: str
    cursor_sequence: int
    operation_version: int
    task_id: str = PROJECTION_TASK_ID
    accountability_id: str = PROJECTION_ACCOUNTABILITY_ID
    schema_version: int = PROJECTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise OperationProjectionError(
                "accepted must be boolean"
            )
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item
            for item in self.reasons
        ):
            raise OperationProjectionError(
                "reasons must contain non-empty strings"
            )
        object.__setattr__(
            self,
            "operation_id",
            _text(self.operation_id, "operation_id", maximum=64),
        )
        object.__setattr__(
            self,
            "tenant_id",
            _text(self.tenant_id, "tenant_id"),
        )
        for field in ("projection_digest", "authority_digest"):
            digest = _text(
                getattr(self, field),
                field,
                maximum=64,
            )
            if len(digest) != 64 or any(
                char not in "0123456789abcdef" for char in digest
            ):
                raise OperationProjectionError(
                    f"{field} must be lowercase sha256"
                )
        object.__setattr__(
            self,
            "cursor_sequence",
            _nonnegative_int(
                self.cursor_sequence,
                "cursor_sequence",
            ),
        )
        object.__setattr__(
            self,
            "operation_version",
            _positive_int(
                self.operation_version,
                "operation_version",
            ),
        )
        if self.task_id != PROJECTION_TASK_ID:
            raise OperationProjectionError("task_id drift")
        if self.accountability_id != PROJECTION_ACCOUNTABILITY_ID:
            raise OperationProjectionError(
                "accountability_id drift"
            )
        if self.schema_version != PROJECTION_SCHEMA_VERSION:
            raise OperationProjectionError(
                "unsupported decision schema version"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "operation_id": self.operation_id,
            "tenant_id": self.tenant_id,
            "projection_digest": self.projection_digest,
            "authority_digest": self.authority_digest,
            "cursor_sequence": self.cursor_sequence,
            "operation_version": self.operation_version,
        }

    @property
    def decision_digest(self) -> str:
        return stable_content_digest(self.payload())

    def accepted_evidence_ref(
        self,
        *,
        source: str = "p1:prod-02:streaming-projection",
    ) -> EvidenceRef:
        if not self.accepted:
            raise OperationProjectionError(
                "rejected projection cannot become promotion evidence"
            )
        return EvidenceRef(
            source=_text(source, "source", maximum=2048),
            digest=self.decision_digest,
            category="streaming_projection_authority",
        )


def start_projection(authority: StoredOperation) -> OperationProjectionState:
    """Create an empty replay projection bound to durable operation identity."""

    if not isinstance(authority, StoredOperation):
        raise TypeError("authority must be StoredOperation")
    baseline = replace(
        authority.envelope,
        state=OperationState.CREATED,
    )
    return OperationProjectionState(
        envelope=baseline,
        operation_version=0,
        cursor_sequence=0,
        initialized=False,
        recent_events=(),
        source="replay",
    )


def resync_projection(
    authority: StoredOperation,
    *,
    stream_latest_sequence: int,
) -> OperationProjectionState:
    """Reset a client to the exact durable state and current stream head."""

    if not isinstance(authority, StoredOperation):
        raise TypeError("authority must be StoredOperation")
    latest = _nonnegative_int(
        stream_latest_sequence,
        "stream_latest_sequence",
    )
    if authority.version < 1:
        raise OperationProjectionError(
            "durable authority version must be positive"
        )
    if latest != authority.version:
        raise ProjectionResyncRequired(
            "stream head sequence does not match durable operation version"
        )
    return OperationProjectionState(
        envelope=authority.envelope,
        operation_version=authority.version,
        cursor_sequence=latest,
        initialized=True,
        recent_events=(),
        source="resync",
    )


def _event_receipt(event: StreamEvent) -> AppliedStreamReceipt:
    return AppliedStreamReceipt(
        sequence=event.sequence,
        event_id=event.event_id,
        event_digest=stable_content_digest(event.as_dict()),
    )


def _event_state(event: StreamEvent) -> tuple[OperationState, int, str]:
    if not isinstance(event, StreamEvent):
        raise TypeError("event must be StreamEvent")
    expected_prefix = "operation."
    if not event.type.startswith(expected_prefix):
        raise ProjectionConflictError(
            "stream event is not an operation state transition"
        )
    raw_state = event.payload.get("state")
    raw_version = event.payload.get("version")
    raw_trace = event.payload.get("trace_id")
    if not isinstance(raw_state, str):
        raise ProjectionConflictError(
            "operation event is missing state"
        )
    try:
        state = OperationState(raw_state)
    except ValueError as exc:
        raise ProjectionConflictError(
            "operation event state is invalid"
        ) from exc
    if event.type != expected_prefix + state.value:
        raise ProjectionConflictError(
            "operation event type/state mismatch"
        )
    version = _positive_int(
        raw_version,
        "event operation version",
    )
    trace_id = _text(
        raw_trace,
        "event trace_id",
        maximum=256,
    )
    return state, version, trace_id


def apply_projection_event(
    projection: OperationProjectionState,
    event: StreamEvent,
) -> OperationProjectionState:
    """Apply one canonical event or reject/resync on any ambiguous history."""

    if not isinstance(projection, OperationProjectionState):
        raise TypeError(
            "projection must be OperationProjectionState"
        )
    if not isinstance(event, StreamEvent):
        raise TypeError("event must be StreamEvent")
    if event.operation_id != projection.operation_id:
        raise ProjectionConflictError(
            "event belongs to a different operation"
        )

    receipt = _event_receipt(event)
    if event.sequence <= projection.cursor_sequence:
        prior = next(
            (
                item
                for item in projection.recent_events
                if item.sequence == event.sequence
            ),
            None,
        )
        if prior is None:
            raise ProjectionResyncRequired(
                "duplicate sequence predates exact receipt window"
            )
        if (
            prior.event_id != receipt.event_id
            or prior.event_digest != receipt.event_digest
        ):
            raise ProjectionConflictError(
                "duplicate sequence conflicts with applied event"
            )
        return projection

    expected_sequence = projection.cursor_sequence + 1
    if event.sequence != expected_sequence:
        raise ProjectionResyncRequired(
            f"stream gap: expected {expected_sequence}, got {event.sequence}"
        )

    target, version, trace_id = _event_state(event)
    if trace_id != projection.trace_id:
        raise ProjectionConflictError(
            "event trace identity mismatch"
        )
    expected_version = projection.operation_version + 1
    if version != expected_version:
        raise ProjectionResyncRequired(
            "operation version does not match contiguous projection"
        )

    if not projection.initialized:
        if version != 1 or target is not OperationState.CREATED:
            raise ProjectionResyncRequired(
                "first replay event must initialize created version 1"
            )
        envelope = replace(
            projection.envelope,
            state=OperationState.CREATED,
        )
    else:
        try:
            envelope = projection.envelope.transition(target)
        except OperationTransitionError as exc:
            raise ProjectionConflictError(
                "event violates canonical operation transition"
            ) from exc

    receipts = (
        *projection.recent_events,
        receipt,
    )[-MAX_EXACT_EVENT_RECEIPTS:]
    return OperationProjectionState(
        envelope=envelope,
        operation_version=version,
        cursor_sequence=event.sequence,
        initialized=True,
        recent_events=receipts,
        source="replay",
    )


def apply_projection_events(
    projection: OperationProjectionState,
    events: Iterable[StreamEvent],
) -> OperationProjectionState:
    """Apply events in delivery order; callers may not sort away corruption."""

    current = projection
    for event in events:
        current = apply_projection_event(current, event)
    return current


def verify_projection_authority(
    projection: OperationProjectionState,
    authority: StoredOperation,
) -> ProjectionAuthorityDecision:
    """Compare derived client state with durable operation authority."""

    if not isinstance(projection, OperationProjectionState):
        raise TypeError(
            "projection must be OperationProjectionState"
        )
    if not isinstance(authority, StoredOperation):
        raise TypeError("authority must be StoredOperation")

    reasons: list[str] = []
    if not projection.initialized:
        reasons.append("projection-not-initialized")
    if projection.operation_id != authority.envelope.operation_id:
        reasons.append("operation-id-mismatch")
    if projection.tenant_id != authority.envelope.tenant_id:
        reasons.append("tenant-id-mismatch")
    if (
        projection.envelope.identity_digest
        != authority.envelope.identity_digest
    ):
        reasons.append("operation-identity-digest-mismatch")
    if projection.trace_id != authority.envelope.trace_id:
        reasons.append("trace-id-mismatch")
    if projection.operation_version != authority.version:
        reasons.append("operation-version-mismatch")
    if projection.cursor_sequence != authority.version:
        reasons.append("stream-cursor-version-mismatch")
    if projection.state is not OperationState(authority.envelope.state):
        reasons.append("operation-state-mismatch")
    if projection.terminal != authority.terminal:
        reasons.append("terminal-state-mismatch")

    authority_digest = stable_content_digest(authority.as_dict())
    normalized = tuple(sorted(set(reasons)))
    return ProjectionAuthorityDecision(
        accepted=not normalized,
        reasons=normalized,
        operation_id=authority.envelope.operation_id,
        tenant_id=authority.envelope.tenant_id,
        projection_digest=projection.projection_digest,
        authority_digest=authority_digest,
        cursor_sequence=projection.cursor_sequence,
        operation_version=authority.version,
    )


__all__ = [
    "MAX_EXACT_EVENT_RECEIPTS",
    "PROJECTION_ACCOUNTABILITY_ID",
    "PROJECTION_SCHEMA_VERSION",
    "PROJECTION_TASK_ID",
    "AppliedStreamReceipt",
    "OperationProjectionError",
    "OperationProjectionState",
    "ProjectionAuthorityDecision",
    "ProjectionConflictError",
    "ProjectionResyncRequired",
    "apply_projection_event",
    "apply_projection_events",
    "resync_projection",
    "start_projection",
    "verify_projection_authority",
]
