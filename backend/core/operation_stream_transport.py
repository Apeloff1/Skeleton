"""Backend-facing transport service for canonical durable AI operations.

This module does not own operation state or event semantics. It composes the
engine-owned durable OperationEnvelope repository, transactional outbox, and
operation stream store into a tenant-bound service suitable for HTTP/SSE
adapters.

Rules:
- durable operation state remains authoritative;
- transport drains committed outbox intent into the canonical stream;
- outbox acknowledgement happens only after durable stream acceptance;
- retry uses deterministic outbox event IDs;
- tenant authorization is checked before status, replay, dispatch, or cancel;
- cancellation transitions the canonical operation state machine and is then
  projected to the stream via the same outbox path.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from skeleton.contracts.operation import OperationState
from skeleton.frontier.operation_stream import (
    ReplayCursor,
    StreamEvent,
    StreamReplayGapError,
)
from skeleton.frontier.operation_stream_store import (
    SQLiteOperationEventStore,
    StreamConsumerCheckpoint,
)
from skeleton.persistence.operation_store import (
    OperationStoreConflict,
    OperationStoreError,
    SQLiteOperationStore,
    StoredOperation,
)


class OperationTransportError(RuntimeError):
    """Base transport-composition error."""


class OperationAccessDenied(OperationTransportError):
    """The caller is not authorized to observe or mutate the operation."""


class OperationTransportConflict(OperationTransportError):
    """A concurrent operation mutation could not be reconciled safely."""


@dataclass(frozen=True, slots=True)
class CancellationResult:
    operation: StoredOperation
    changed: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "changed": self.changed,
            "operation": self.operation.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class OperationResyncSnapshot:
    operation: StoredOperation
    compacted_through: int
    latest_sequence: int
    stream_terminal: bool
    active_consumer_count: int

    @property
    def resume_after_sequence(self) -> int:
        return self.compacted_through

    def as_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation.as_dict(),
            "compacted_through": self.compacted_through,
            "resume_after_sequence": self.resume_after_sequence,
            "latest_sequence": self.latest_sequence,
            "terminal": self.operation.terminal or self.stream_terminal,
            "active_consumer_count": self.active_consumer_count,
        }


@dataclass(frozen=True, slots=True)
class OperationAcknowledgement:
    consumer: StreamConsumerCheckpoint
    compacted_events: int
    compacted_through: int
    latest_sequence: int
    active_consumer_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "consumer": self.consumer.as_dict(),
            "compacted_events": self.compacted_events,
            "compacted_through": self.compacted_through,
            "latest_sequence": self.latest_sequence,
            "active_consumer_count": self.active_consumer_count,
        }


@dataclass(frozen=True, slots=True)
class OperationStreamBatch:
    operation: StoredOperation
    events: tuple[StreamEvent, ...]
    after_sequence: int
    stream_latest_sequence: int
    stream_terminal: bool

    @property
    def latest_sequence(self) -> int:
        if self.events:
            return self.events[-1].sequence
        return self.after_sequence

    @property
    def has_more(self) -> bool:
        return self.latest_sequence < self.stream_latest_sequence

    @property
    def terminal(self) -> bool:
        # Operation authority may already be terminal while the durable outbox
        # still has undispatched/replay-unread events. A transport batch is
        # terminal only after the canonical stream itself is terminal and this
        # client has caught up to the stream head.
        return (
            self.operation.terminal
            and self.stream_terminal
            and not self.has_more
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation.as_dict(),
            "events": [event.as_dict() for event in self.events],
            "after_sequence": self.after_sequence,
            "latest_sequence": self.latest_sequence,
            "stream_latest_sequence": self.stream_latest_sequence,
            "has_more": self.has_more,
            "terminal": self.terminal,
        }


def _tenant(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OperationAccessDenied("operation is not accessible")
    normalized = value.strip()
    if len(normalized) > 512:
        raise OperationAccessDenied("operation is not accessible")
    return normalized


def encode_sse_event(event: StreamEvent) -> str:
    """Encode one canonical event as strict single-record SSE."""

    payload = json.dumps(
        event.as_dict(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return (
        f"id: {event.sequence}\n"
        f"event: {event.type}\n"
        f"data: {payload}\n\n"
    )


def encode_sse_heartbeat() -> str:
    """Return a comment heartbeat that does not advance the replay cursor."""

    return ": heartbeat\n\n"


def operation_runtime_paths(
    source: Mapping[str, str] | None = None,
) -> tuple[Path, Path]:
    """Resolve one shared local durable runtime directory without hidden CWD state."""

    environ = os.environ if source is None else source
    root_raw = environ.get("CODEDOCK_OPERATION_RUNTIME_DIR", "").strip()
    root = (
        Path(root_raw).expanduser()
        if root_raw
        else Path(tempfile.gettempdir()) / "codedock-operation-runtime"
    )
    state_raw = environ.get("CODEDOCK_OPERATION_STATE_DB", "").strip()
    stream_raw = environ.get("CODEDOCK_OPERATION_STREAM_DB", "").strip()
    state_path = Path(state_raw).expanduser() if state_raw else root / "operations.sqlite3"
    stream_path = Path(stream_raw).expanduser() if stream_raw else root / "events.sqlite3"
    if state_path == stream_path:
        raise OperationTransportError(
            "operation state and stream databases must use separate files"
        )
    return state_path, stream_path


def transport_from_env(
    source: Mapping[str, str] | None = None,
) -> "OperationStreamTransport":
    """Create a durable local transport using the canonical environment paths."""

    state_path, stream_path = operation_runtime_paths(source)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    stream_path.parent.mkdir(parents=True, exist_ok=True)
    return OperationStreamTransport(
        SQLiteOperationStore(state_path),
        SQLiteOperationEventStore(stream_path),
    )


class OperationStreamTransport:
    """Tenant-bound bridge from durable operation state to resumable events."""

    def __init__(
        self,
        operation_store: SQLiteOperationStore,
        event_store: SQLiteOperationEventStore,
    ) -> None:
        if not isinstance(operation_store, SQLiteOperationStore):
            raise TypeError("operation_store must be SQLiteOperationStore")
        if not isinstance(event_store, SQLiteOperationEventStore):
            raise TypeError("event_store must be SQLiteOperationEventStore")
        self.operation_store = operation_store
        self.event_store = event_store

    def _authorized_operation(
        self,
        operation_id: str,
        *,
        tenant_id: str,
    ) -> StoredOperation:
        tenant = _tenant(tenant_id)
        try:
            operation = self.operation_store.get(operation_id)
        except OperationStoreError as exc:
            raise OperationAccessDenied("operation is not accessible") from exc
        if operation.envelope.tenant_id != tenant:
            raise OperationAccessDenied("operation is not accessible")
        return operation

    def status(
        self,
        operation_id: str,
        *,
        tenant_id: str,
    ) -> StoredOperation:
        return self._authorized_operation(operation_id, tenant_id=tenant_id)

    def dispatch_pending(
        self,
        operation_id: str,
        *,
        tenant_id: str,
        limit: int = 1000,
    ) -> tuple[StreamEvent, ...]:
        """Project committed outbox rows into the durable stream and ack them."""

        self._authorized_operation(operation_id, tenant_id=tenant_id)
        pending = self.operation_store.pending_outbox(
            operation_id=operation_id,
            limit=limit,
        )
        delivered: list[StreamEvent] = []
        for item in pending:
            event = self.event_store.append(
                item.operation_id,
                item.event_type,
                item.payload,
                event_id=item.outbox_id,
                timestamp=item.created_at,
            )
            self.operation_store.acknowledge_outbox(item.outbox_id)
            delivered.append(event)
        return tuple(delivered)

    def replay(
        self,
        operation_id: str,
        *,
        tenant_id: str,
        after_sequence: int = 0,
        limit: int = 1000,
        consumer_id: str | None = None,
        consumer_lease_seconds: int = 300,
    ) -> OperationStreamBatch:
        """Drain committed state transitions, then replay events after cursor."""

        operation = self._authorized_operation(
            operation_id,
            tenant_id=tenant_id,
        )
        if consumer_id is not None:
            self.event_store.register_consumer(
                operation_id,
                consumer_id,
                lease_seconds=consumer_lease_seconds,
            )
        # Projection depth is independent from the caller's replay page size.
        # Otherwise a page of N events can make the durable head appear to be N
        # even when additional committed outbox transitions already exist,
        # incorrectly reporting has_more=False across reconnects/workers.
        self.dispatch_pending(
            operation_id,
            tenant_id=tenant_id,
        )
        events = self.event_store.replay(
            ReplayCursor(
                operation_id=operation_id,
                after_sequence=after_sequence,
            ),
            limit=limit,
        )
        # Re-read after dispatch/cancellation races so operation authority is
        # never older than the events just returned. Read the stream head too:
        # a terminal operation can still have undispatched/unread durable events
        # when replay is intentionally batch-limited for backpressure.
        operation = self._authorized_operation(
            operation_id,
            tenant_id=tenant_id,
        )
        head = self.event_store.head(operation_id)
        return OperationStreamBatch(
            operation=operation,
            events=events,
            after_sequence=after_sequence,
            stream_latest_sequence=int(head["latest_sequence"]),
            stream_terminal=bool(head["terminal"]),
        )

    def resync_snapshot(
        self,
        operation_id: str,
        *,
        tenant_id: str,
        consumer_id: str | None = None,
        consumer_lease_seconds: int = 300,
    ) -> OperationResyncSnapshot:
        """Return authoritative operation state plus the safe retained replay floor."""

        operation = self._authorized_operation(
            operation_id,
            tenant_id=tenant_id,
        )
        # Project any committed outbox rows before publishing the head so the
        # snapshot cannot report an older durable stream position than state.
        self.dispatch_pending(
            operation_id,
            tenant_id=tenant_id,
        )
        if consumer_id is not None:
            self.event_store.register_consumer(
                operation_id,
                consumer_id,
                lease_seconds=consumer_lease_seconds,
            )
        head = self.event_store.head(operation_id)
        consumers = self.event_store.active_consumers(operation_id)
        return OperationResyncSnapshot(
            operation=self._authorized_operation(
                operation_id,
                tenant_id=tenant_id,
            ),
            compacted_through=int(head["compacted_through"]),
            latest_sequence=int(head["latest_sequence"]),
            stream_terminal=bool(head["terminal"]),
            active_consumer_count=len(consumers),
        )

    def acknowledge_and_compact(
        self,
        operation_id: str,
        *,
        tenant_id: str,
        consumer_id: str,
        sequence: int,
        consumer_lease_seconds: int = 300,
    ) -> OperationAcknowledgement:
        """ACK one applied cursor and compact only through all active clients."""

        checkpoint = self.acknowledge(
            operation_id,
            tenant_id=tenant_id,
            consumer_id=consumer_id,
            sequence=sequence,
            consumer_lease_seconds=consumer_lease_seconds,
        )
        compacted = self.compact_acknowledged(
            operation_id,
            tenant_id=tenant_id,
        )
        head = self.event_store.head(operation_id)
        consumers = self.event_store.active_consumers(operation_id)
        return OperationAcknowledgement(
            consumer=checkpoint,
            compacted_events=compacted,
            compacted_through=int(head["compacted_through"]),
            latest_sequence=int(head["latest_sequence"]),
            active_consumer_count=len(consumers),
        )

    def acknowledge(
        self,
        operation_id: str,
        *,
        tenant_id: str,
        consumer_id: str,
        sequence: int,
        consumer_lease_seconds: int = 300,
    ) -> StreamConsumerCheckpoint:
        """Advance one tenant-owned consumer cursor after client-side apply."""

        self._authorized_operation(operation_id, tenant_id=tenant_id)
        return self.event_store.acknowledge_consumer(
            operation_id,
            consumer_id,
            sequence,
            lease_seconds=consumer_lease_seconds,
        )

    def compact_acknowledged(
        self,
        operation_id: str,
        *,
        tenant_id: str,
    ) -> int:
        """Compact only history acknowledged by every active consumer."""

        self._authorized_operation(operation_id, tenant_id=tenant_id)
        return self.event_store.compact_acknowledged(operation_id)

    def cancel(
        self,
        operation_id: str,
        *,
        tenant_id: str,
    ) -> CancellationResult:
        """Cancel the canonical operation, idempotently across terminal races."""

        current = self._authorized_operation(
            operation_id,
            tenant_id=tenant_id,
        )
        if current.terminal:
            self.dispatch_pending(operation_id, tenant_id=tenant_id)
            return CancellationResult(operation=current, changed=False)

        try:
            cancelled = self.operation_store.transition(
                operation_id,
                OperationState.CANCELLED,
                expected_version=current.version,
            )
        except OperationStoreConflict as exc:
            latest = self._authorized_operation(
                operation_id,
                tenant_id=tenant_id,
            )
            if latest.terminal:
                self.dispatch_pending(operation_id, tenant_id=tenant_id)
                return CancellationResult(operation=latest, changed=False)
            raise OperationTransportConflict(
                "operation changed during cancellation"
            ) from exc

        self.dispatch_pending(operation_id, tenant_id=tenant_id)
        return CancellationResult(operation=cancelled, changed=True)


__all__ = [
    "CancellationResult",
    "OperationAcknowledgement",
    "OperationAccessDenied",
    "OperationResyncSnapshot",
    "OperationStreamBatch",
    "OperationStreamTransport",
    "OperationTransportConflict",
    "StreamConsumerCheckpoint",
    "OperationTransportError",
    "StreamReplayGapError",
    "encode_sse_event",
    "encode_sse_heartbeat",
    "operation_runtime_paths",
    "transport_from_env",
]
