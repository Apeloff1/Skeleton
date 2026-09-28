"""P1 durable streaming projection authority.

The operation repository remains the owner of operation truth. This module is
a non-authoritative consumer/reducer contract for P1-PROD-02: it proves that
replay pages and resync snapshots reconstruct one deterministic product-facing
projection without allowing delivery order, duplicates, reconnects, or local
state to invent canonical operation state.

Normal replay and authoritative resync may have different evidence histories,
but their truth digests must converge when they represent the same durable
operation head.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Any, Iterable
from uuid import UUID

from skeleton.contracts.canonical import EvidenceRef
from skeleton.contracts.operation import OperationState, TERMINAL_OPERATION_STATES
from skeleton.frontier.operation_stream import StreamEvent

from core.operation_stream_transport import (
    OperationResyncSnapshot,
    OperationStreamBatch,
)


STREAM_PROJECTION_SCHEMA_VERSION = 1
STREAM_PROJECTION_TASK_ID = "P1-PROD-02"
STREAM_PROJECTION_ACCOUNTABILITY_ID = "ACC-P1-PROD-02"


class ProjectionAuthorityError(ValueError):
    """Projection input or evidence violates the durable-stream contract."""


class ProjectionSource(str, Enum):
    BOOTSTRAP = "bootstrap"
    REPLAY = "replay"
    RESYNC = "resync"


def _text(value: object, field: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProjectionAuthorityError(f"{field} must be non-empty")
    normalized = value.strip()
    if normalized != value or len(normalized) > maximum:
        raise ProjectionAuthorityError(f"{field} must be normalized")
    return normalized


def _uuid(value: object, field: str) -> str:
    text = _text(value, field, maximum=64)
    try:
        parsed = UUID(text)
    except (ValueError, AttributeError) as exc:
        raise ProjectionAuthorityError(f"{field} must be a canonical UUID") from exc
    if str(parsed) != text:
        raise ProjectionAuthorityError(f"{field} must be a canonical UUID")
    return text


def _sha256(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise ProjectionAuthorityError(f"{field} must be lowercase sha256")
    return value


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProjectionAuthorityError(f"{field} must be a non-negative integer")
    return value


def _canonical_digest(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProjectionAuthorityError(
            "projection payload must be canonical JSON"
        ) from exc
    return hashlib.sha256(raw).hexdigest()


def _event_digest(event: StreamEvent) -> str:
    if not isinstance(event, StreamEvent):
        raise ProjectionAuthorityError("events must contain StreamEvent")
    return _canonical_digest(event.as_dict())


def _chain(previous: str, marker: str, digest: str) -> str:
    return hashlib.sha256(
        (previous + "\0" + marker + "\0" + digest).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class OperationProjection:
    operation_id: str
    tenant_id: str
    state: OperationState | None
    operation_version: int
    applied_through: int
    stream_latest_sequence: int
    terminal: bool
    trace_id: str | None
    evidence_chain_digest: str
    source: ProjectionSource = ProjectionSource.BOOTSTRAP
    resync_generation: int = 0
    schema_version: int = STREAM_PROJECTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "operation_id",
            _uuid(self.operation_id, "operation_id"),
        )
        object.__setattr__(
            self,
            "tenant_id",
            _text(self.tenant_id, "tenant_id"),
        )
        if self.state is not None:
            try:
                object.__setattr__(self, "state", OperationState(self.state))
            except ValueError as exc:
                raise ProjectionAuthorityError("invalid operation state") from exc
        object.__setattr__(
            self,
            "operation_version",
            _nonnegative_int(self.operation_version, "operation_version"),
        )
        object.__setattr__(
            self,
            "applied_through",
            _nonnegative_int(self.applied_through, "applied_through"),
        )
        object.__setattr__(
            self,
            "stream_latest_sequence",
            _nonnegative_int(
                self.stream_latest_sequence,
                "stream_latest_sequence",
            ),
        )
        if self.stream_latest_sequence < self.applied_through:
            raise ProjectionAuthorityError(
                "stream_latest_sequence cannot precede applied_through"
            )
        if not isinstance(self.terminal, bool):
            raise ProjectionAuthorityError("terminal must be boolean")
        if self.trace_id is not None:
            object.__setattr__(
                self,
                "trace_id",
                _text(self.trace_id, "trace_id", maximum=256),
            )
        object.__setattr__(
            self,
            "evidence_chain_digest",
            _sha256(self.evidence_chain_digest, "evidence_chain_digest"),
        )
        try:
            object.__setattr__(self, "source", ProjectionSource(self.source))
        except ValueError as exc:
            raise ProjectionAuthorityError("invalid projection source") from exc
        object.__setattr__(
            self,
            "resync_generation",
            _nonnegative_int(self.resync_generation, "resync_generation"),
        )
        if self.schema_version != STREAM_PROJECTION_SCHEMA_VERSION:
            raise ProjectionAuthorityError("unsupported schema version")
        if self.state is None:
            if self.operation_version != 0 or self.applied_through != 0:
                raise ProjectionAuthorityError(
                    "empty projection cannot claim operation progress"
                )
            if self.terminal or self.trace_id is not None:
                raise ProjectionAuthorityError(
                    "empty projection cannot claim terminal or trace state"
                )
        else:
            if self.operation_version < 1 or self.applied_through < 1:
                raise ProjectionAuthorityError(
                    "materialized projection requires positive version/cursor"
                )
            state_terminal = self.state in TERMINAL_OPERATION_STATES
            if state_terminal and not self.terminal:
                raise ProjectionAuthorityError(
                    "terminal operation state must project terminal"
                )

    def truth_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "operation_id": self.operation_id,
            "tenant_id": self.tenant_id,
            "state": None if self.state is None else self.state.value,
            "operation_version": self.operation_version,
            "applied_through": self.applied_through,
            "stream_latest_sequence": self.stream_latest_sequence,
            "terminal": self.terminal,
            "trace_id": self.trace_id,
        }

    @property
    def truth_digest(self) -> str:
        return _canonical_digest(self.truth_payload())

    def evidence_payload(self) -> dict[str, Any]:
        return {
            **self.truth_payload(),
            "evidence_chain_digest": self.evidence_chain_digest,
            "source": self.source.value,
            "resync_generation": self.resync_generation,
        }

    @property
    def projection_digest(self) -> str:
        return _canonical_digest(self.evidence_payload())


@dataclass(frozen=True, slots=True)
class ProjectionDecision:
    accepted: bool
    reasons: tuple[str, ...]
    before_digest: str
    after: OperationProjection
    normalized_event_digests: tuple[str, ...]
    input_digest: str
    task_id: str = STREAM_PROJECTION_TASK_ID
    accountability_id: str = STREAM_PROJECTION_ACCOUNTABILITY_ID
    schema_version: int = STREAM_PROJECTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise ProjectionAuthorityError("accepted must be boolean")
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item for item in self.reasons
        ):
            raise ProjectionAuthorityError(
                "reasons must contain non-empty strings"
            )
        object.__setattr__(
            self,
            "before_digest",
            _sha256(self.before_digest, "before_digest"),
        )
        if not isinstance(self.after, OperationProjection):
            raise ProjectionAuthorityError("after must be OperationProjection")
        if not isinstance(self.normalized_event_digests, tuple):
            raise ProjectionAuthorityError(
                "normalized_event_digests must be a tuple"
            )
        for digest in self.normalized_event_digests:
            _sha256(digest, "normalized_event_digest")
        object.__setattr__(
            self,
            "input_digest",
            _sha256(self.input_digest, "input_digest"),
        )
        if self.task_id != STREAM_PROJECTION_TASK_ID:
            raise ProjectionAuthorityError("task_id drift")
        if self.accountability_id != STREAM_PROJECTION_ACCOUNTABILITY_ID:
            raise ProjectionAuthorityError("accountability_id drift")
        if self.schema_version != STREAM_PROJECTION_SCHEMA_VERSION:
            raise ProjectionAuthorityError("unsupported schema version")
        if not self.accepted and self.after.projection_digest != self.before_digest:
            raise ProjectionAuthorityError(
                "rejected projection decision cannot mutate state"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "before_digest": self.before_digest,
            "after_digest": self.after.projection_digest,
            "truth_digest": self.after.truth_digest,
            "normalized_event_digests": list(self.normalized_event_digests),
            "input_digest": self.input_digest,
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())

    def accepted_evidence_ref(
        self,
        *,
        source: str = "p1:prod-02:stream-projection",
    ) -> EvidenceRef:
        if not self.accepted:
            raise ProjectionAuthorityError(
                "rejected projection cannot become promotion evidence"
            )
        return EvidenceRef(
            source=_text(source, "source"),
            digest=self.decision_digest,
            category="stream_projection_authority",
        )


def bootstrap_projection(
    operation_id: str,
    *,
    tenant_id: str,
) -> OperationProjection:
    operation = _uuid(operation_id, "operation_id")
    tenant = _text(tenant_id, "tenant_id")
    genesis = _canonical_digest(
        {
            "contract": "p1-prod-02-projection-genesis",
            "operation_id": operation,
            "tenant_id": tenant,
        }
    )
    return OperationProjection(
        operation_id=operation,
        tenant_id=tenant,
        state=None,
        operation_version=0,
        applied_through=0,
        stream_latest_sequence=0,
        terminal=False,
        trace_id=None,
        evidence_chain_digest=genesis,
    )


def _normalize_events(
    events: Iterable[StreamEvent],
    *,
    operation_id: str,
) -> tuple[tuple[StreamEvent, ...], tuple[str, ...], tuple[str, ...]]:
    if isinstance(events, (str, bytes)):
        raise ProjectionAuthorityError("events must contain StreamEvent")
    by_sequence: dict[int, tuple[StreamEvent, str]] = {}
    by_id: dict[str, tuple[int, str]] = {}
    reasons: list[str] = []

    for event in events:
        if not isinstance(event, StreamEvent):
            raise ProjectionAuthorityError("events must contain StreamEvent")
        digest = _event_digest(event)
        if event.operation_id != operation_id:
            reasons.append(f"event-operation-mismatch:{event.sequence}")
            continue

        prior_seq = by_sequence.get(event.sequence)
        if prior_seq is not None:
            if prior_seq[1] != digest:
                reasons.append(
                    f"conflicting-duplicate-sequence:{event.sequence}"
                )
            continue

        prior_id = by_id.get(event.event_id)
        if prior_id is not None:
            if prior_id != (event.sequence, digest):
                reasons.append(
                    f"conflicting-duplicate-event-id:{event.event_id}"
                )
            continue

        by_sequence[event.sequence] = (event, digest)
        by_id[event.event_id] = (event.sequence, digest)

    ordered = tuple(
        item[0] for _, item in sorted(by_sequence.items())
    )
    digests = tuple(
        item[1] for _, item in sorted(by_sequence.items())
    )
    return ordered, digests, tuple(sorted(set(reasons)))


def _batch_input_digest(
    batch: OperationStreamBatch,
    event_digests: tuple[str, ...],
) -> str:
    return _canonical_digest(
        {
            "operation": batch.operation.as_dict(),
            "after_sequence": batch.after_sequence,
            "stream_latest_sequence": batch.stream_latest_sequence,
            "stream_terminal": batch.stream_terminal,
            "normalized_event_digests": list(event_digests),
        }
    )


def apply_stream_batch(
    projection: OperationProjection,
    batch: OperationStreamBatch,
) -> ProjectionDecision:
    """Apply one replay page after canonical sorting and deduplication."""

    if not isinstance(projection, OperationProjection):
        raise TypeError("projection must be OperationProjection")
    if not isinstance(batch, OperationStreamBatch):
        raise TypeError("batch must be OperationStreamBatch")

    events, digests, normalization_reasons = _normalize_events(
        batch.events,
        operation_id=projection.operation_id,
    )
    input_digest = _batch_input_digest(batch, digests)
    reasons: list[str] = list(normalization_reasons)

    operation = batch.operation
    if operation.envelope.operation_id != projection.operation_id:
        reasons.append("batch-operation-mismatch")
    if operation.envelope.tenant_id != projection.tenant_id:
        reasons.append("batch-tenant-mismatch")
    if batch.after_sequence != projection.applied_through:
        reasons.append("cursor-mismatch")
    if batch.stream_latest_sequence < projection.applied_through:
        reasons.append("stream-head-regressed")
    if events and batch.stream_latest_sequence < events[-1].sequence:
        reasons.append("event-beyond-stream-head")
    if not events and batch.stream_latest_sequence > projection.applied_through:
        reasons.append("empty-batch-before-stream-head")

    current_state = projection.state
    current_version = projection.operation_version
    current_trace = projection.trace_id
    applied = projection.applied_through
    chain = projection.evidence_chain_digest
    terminal = projection.terminal

    if not reasons:
        expected_sequence = applied + 1
        for event, digest in zip(events, digests, strict=True):
            if event.sequence != expected_sequence:
                reasons.append(
                    f"sequence-gap:expected-{expected_sequence}:got-{event.sequence}"
                )
                break
            payload = dict(event.payload)
            raw_state = payload.get("state")
            raw_version = payload.get("version")
            raw_trace = payload.get("trace_id")
            try:
                event_state = OperationState(raw_state)
            except (ValueError, TypeError):
                reasons.append(f"event-state-invalid:{event.sequence}")
                break
            if (
                isinstance(raw_version, bool)
                or not isinstance(raw_version, int)
                or raw_version < 1
            ):
                reasons.append(f"event-version-invalid:{event.sequence}")
                break
            if not isinstance(raw_trace, str) or not raw_trace.strip():
                reasons.append(f"event-trace-invalid:{event.sequence}")
                break
            if event.type != f"operation.{event_state.value}":
                reasons.append(f"event-type-state-mismatch:{event.sequence}")
                break
            if raw_version != current_version + 1:
                reasons.append(
                    f"operation-version-gap:expected-{current_version + 1}:got-{raw_version}"
                )
                break
            normalized_trace = raw_trace.strip()
            if normalized_trace != raw_trace or len(normalized_trace) > 256:
                reasons.append(f"event-trace-invalid:{event.sequence}")
                break
            if current_trace is not None and normalized_trace != current_trace:
                reasons.append(f"trace-id-drift:{event.sequence}")
                break
            if terminal:
                reasons.append(f"event-after-terminal:{event.sequence}")
                break

            current_state = event_state
            current_version = raw_version
            current_trace = normalized_trace
            applied = event.sequence
            terminal = event_state in TERMINAL_OPERATION_STATES
            chain = _chain(chain, f"event:{event.sequence}", digest)
            expected_sequence += 1

    if not reasons and applied == batch.stream_latest_sequence:
        if current_state != operation.envelope.state:
            reasons.append("caught-up-state-mismatch")
        if current_version != operation.version:
            reasons.append("caught-up-version-mismatch")
        if current_trace != operation.envelope.trace_id:
            reasons.append("caught-up-trace-mismatch")
        authoritative_terminal = operation.terminal or batch.stream_terminal
        if terminal != authoritative_terminal:
            reasons.append("caught-up-terminal-mismatch")

    before_digest = projection.projection_digest
    if reasons:
        return ProjectionDecision(
            accepted=False,
            reasons=tuple(sorted(set(reasons))),
            before_digest=before_digest,
            after=projection,
            normalized_event_digests=digests,
            input_digest=input_digest,
        )

    after = OperationProjection(
        operation_id=projection.operation_id,
        tenant_id=projection.tenant_id,
        state=current_state,
        operation_version=current_version,
        applied_through=applied,
        stream_latest_sequence=batch.stream_latest_sequence,
        terminal=terminal,
        trace_id=current_trace,
        evidence_chain_digest=chain,
        source=ProjectionSource.REPLAY,
        resync_generation=projection.resync_generation,
    )
    return ProjectionDecision(
        accepted=True,
        reasons=(),
        before_digest=before_digest,
        after=after,
        normalized_event_digests=digests,
        input_digest=input_digest,
    )


def apply_resync_snapshot(
    projection: OperationProjection,
    snapshot: OperationResyncSnapshot,
) -> ProjectionDecision:
    """Reset from durable operation truth after a replay compaction gap.

    The snapshot already represents the authoritative operation head, so the
    projection advances directly to latest_sequence rather than replaying
    retained historical events that are already reflected in that snapshot.
    """

    if not isinstance(projection, OperationProjection):
        raise TypeError("projection must be OperationProjection")
    if not isinstance(snapshot, OperationResyncSnapshot):
        raise TypeError("snapshot must be OperationResyncSnapshot")

    operation = snapshot.operation
    reasons: list[str] = []
    if operation.envelope.operation_id != projection.operation_id:
        reasons.append("resync-operation-mismatch")
    if operation.envelope.tenant_id != projection.tenant_id:
        reasons.append("resync-tenant-mismatch")
    if snapshot.compacted_through > snapshot.latest_sequence:
        reasons.append("resync-compaction-beyond-head")
    if snapshot.latest_sequence < projection.applied_through:
        reasons.append("resync-head-regressed")

    snapshot_payload = snapshot.as_dict()
    input_digest = _canonical_digest(snapshot_payload)
    before_digest = projection.projection_digest
    if reasons:
        return ProjectionDecision(
            accepted=False,
            reasons=tuple(sorted(set(reasons))),
            before_digest=before_digest,
            after=projection,
            normalized_event_digests=(),
            input_digest=input_digest,
        )

    chain = _chain(
        projection.evidence_chain_digest,
        f"resync:{projection.resync_generation + 1}",
        input_digest,
    )
    terminal = operation.terminal or snapshot.stream_terminal
    after = OperationProjection(
        operation_id=projection.operation_id,
        tenant_id=projection.tenant_id,
        state=operation.envelope.state,
        operation_version=operation.version,
        applied_through=snapshot.latest_sequence,
        stream_latest_sequence=snapshot.latest_sequence,
        terminal=terminal,
        trace_id=operation.envelope.trace_id,
        evidence_chain_digest=chain,
        source=ProjectionSource.RESYNC,
        resync_generation=projection.resync_generation + 1,
    )
    return ProjectionDecision(
        accepted=True,
        reasons=(),
        before_digest=before_digest,
        after=after,
        normalized_event_digests=(),
        input_digest=input_digest,
    )


__all__ = [
    "STREAM_PROJECTION_ACCOUNTABILITY_ID",
    "STREAM_PROJECTION_SCHEMA_VERSION",
    "STREAM_PROJECTION_TASK_ID",
    "OperationProjection",
    "ProjectionAuthorityError",
    "ProjectionDecision",
    "ProjectionSource",
    "apply_resync_snapshot",
    "apply_stream_batch",
    "bootstrap_projection",
]
