"""Canonical resumable event protocol for long-running AI operations.

This module defines the transport-neutral contract used by future SSE,
WebSocket, polling, and durable-stream adapters. It deliberately contains no
HTTP framework code.

The in-memory log is a reference implementation and conformance oracle. It
fails closed on overflow instead of silently dropping events, supports cursor
replay, rejects post-terminal writes, and detects duplicate event-ID conflicts.
Production durable transports may replace storage while preserving these
semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any, Mapping
from uuid import UUID, uuid4


STREAM_SCHEMA_VERSION = 1
MAX_STREAM_EVENT_BYTES = 128_000
TERMINAL_EVENT_TYPES = frozenset(
    {
        "operation.completed",
        "operation.failed",
        "operation.cancelled",
    }
)


class StreamContractError(ValueError):
    """Base error for canonical stream contract violations."""


class StreamBackpressureError(StreamContractError):
    """Publisher attempted to exceed the bounded retained-event window."""


class StreamReplayGapError(StreamContractError):
    """A requested cursor predates retained history and cannot be resumed safely."""


class StreamTerminalError(StreamContractError):
    """An event was appended after an operation already emitted a terminal event."""


class StreamDuplicateConflictError(StreamContractError):
    """An event ID was reused for non-identical event content."""


def _text(value: object, field_name: str, *, max_length: int = 512) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StreamContractError(f"{field_name} must be a non-empty string")
    normalized = value.strip()
    if normalized != value:
        raise StreamContractError(f"{field_name} must be normalized")
    if len(normalized) > max_length:
        raise StreamContractError(f"{field_name} exceeds maximum length")
    return normalized


def _uuid(value: object, field_name: str) -> str:
    text = _text(value, field_name, max_length=64)
    try:
        parsed = UUID(text)
    except (ValueError, AttributeError) as exc:
        raise StreamContractError(f"{field_name} must be a canonical UUID") from exc
    if str(parsed) != text:
        raise StreamContractError(f"{field_name} must be a canonical UUID")
    return text


def _timestamp(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise StreamContractError("timestamp must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise StreamContractError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class StreamEvent:
    operation_id: str
    event_id: str
    sequence: int
    type: str
    timestamp: datetime
    payload: Mapping[str, Any]
    schema_version: int = STREAM_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _uuid(self.operation_id, "operation_id")
        _uuid(self.event_id, "event_id")
        if self.schema_version != STREAM_SCHEMA_VERSION:
            raise StreamContractError("unsupported stream schema version")
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int):
            raise StreamContractError("sequence must be an integer")
        if self.sequence < 1:
            raise StreamContractError("sequence must be positive")
        _text(self.type, "type", max_length=128)
        _timestamp(self.timestamp)
        if not isinstance(self.payload, Mapping):
            raise StreamContractError("payload must be a mapping")
        try:
            encoded = json.dumps(
                dict(self.payload),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise StreamContractError("payload must be strict JSON") from exc
        if len(encoded) > MAX_STREAM_EVENT_BYTES:
            raise StreamContractError("stream event payload exceeds byte budget")

    @property
    def terminal(self) -> bool:
        return self.type in TERMINAL_EVENT_TYPES

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "operation_id": self.operation_id,
            "event_id": self.event_id,
            "sequence": self.sequence,
            "type": self.type,
            "timestamp": _timestamp(self.timestamp).isoformat(),
            "payload": dict(self.payload),
        }


@dataclass(frozen=True, slots=True)
class ReplayCursor:
    operation_id: str
    after_sequence: int = 0

    def __post_init__(self) -> None:
        _uuid(self.operation_id, "operation_id")
        if isinstance(self.after_sequence, bool) or not isinstance(
            self.after_sequence, int
        ):
            raise StreamContractError("after_sequence must be an integer")
        if self.after_sequence < 0:
            raise StreamContractError("after_sequence must not be negative")


class OperationEventLog:
    """Bounded reference event log with explicit replay/backpressure semantics."""

    def __init__(self, operation_id: str, *, capacity: int = 1024) -> None:
        self.operation_id = _uuid(operation_id, "operation_id")
        if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 1:
            raise StreamContractError("capacity must be a positive integer")
        self.capacity = capacity
        self._events: list[StreamEvent] = []
        self._by_id: dict[str, StreamEvent] = {}
        self._compacted_through = 0
        self._terminal = False

    @property
    def next_sequence(self) -> int:
        if self._events:
            return self._events[-1].sequence + 1
        return self._compacted_through + 1

    @property
    def terminal(self) -> bool:
        return self._terminal

    @property
    def retained_range(self) -> tuple[int, int]:
        if not self._events:
            return (self._compacted_through + 1, self._compacted_through)
        return (self._events[0].sequence, self._events[-1].sequence)

    def append(
        self,
        event_type: str,
        payload: Mapping[str, Any],
        *,
        event_id: str | None = None,
        timestamp: datetime | None = None,
    ) -> StreamEvent:
        if self._terminal:
            raise StreamTerminalError("operation stream is already terminal")
        if len(self._events) >= self.capacity:
            raise StreamBackpressureError(
                "operation event buffer is full; compact acknowledged history before publishing"
            )
        event = StreamEvent(
            operation_id=self.operation_id,
            event_id=event_id or str(uuid4()),
            sequence=self.next_sequence,
            type=event_type,
            timestamp=timestamp or datetime.now(timezone.utc),
            payload=dict(payload),
        )
        prior = self._by_id.get(event.event_id)
        if prior is not None:
            if prior.as_dict() == event.as_dict():
                return prior
            raise StreamDuplicateConflictError(
                "event_id already exists with different event content"
            )
        self._events.append(event)
        self._by_id[event.event_id] = event
        if event.terminal:
            self._terminal = True
        return event

    def append_event(self, event: StreamEvent) -> StreamEvent:
        """Append a pre-built event from a durable or remote producer."""

        if event.operation_id != self.operation_id:
            raise StreamContractError("event belongs to a different operation")
        prior = self._by_id.get(event.event_id)
        if prior is not None:
            if prior.as_dict() == event.as_dict():
                return prior
            raise StreamDuplicateConflictError(
                "event_id already exists with different event content"
            )
        if self._terminal:
            raise StreamTerminalError("operation stream is already terminal")
        if event.sequence != self.next_sequence:
            raise StreamContractError(
                f"out-of-order stream sequence: expected {self.next_sequence}, got {event.sequence}"
            )
        if len(self._events) >= self.capacity:
            raise StreamBackpressureError(
                "operation event buffer is full; compact acknowledged history before publishing"
            )
        self._events.append(event)
        self._by_id[event.event_id] = event
        if event.terminal:
            self._terminal = True
        return event

    def replay(self, cursor: ReplayCursor | None = None) -> tuple[StreamEvent, ...]:
        if cursor is None:
            after = self._compacted_through
        else:
            if cursor.operation_id != self.operation_id:
                raise StreamContractError("replay cursor belongs to a different operation")
            after = cursor.after_sequence

        if after < self._compacted_through:
            raise StreamReplayGapError(
                "requested replay cursor predates retained history"
            )
        return tuple(event for event in self._events if event.sequence > after)

    def compact_through(self, sequence: int) -> int:
        """Drop history acknowledged durable or consumed through sequence."""

        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise StreamContractError("compaction sequence must be a non-negative integer")
        if self._events and sequence > self._events[-1].sequence:
            raise StreamContractError("cannot compact beyond the latest event")
        if sequence < self._compacted_through:
            return 0

        removed = [event for event in self._events if event.sequence <= sequence]
        self._events = [event for event in self._events if event.sequence > sequence]
        for event in removed:
            self._by_id.pop(event.event_id, None)
        self._compacted_through = max(self._compacted_through, sequence)
        return len(removed)


__all__ = [
    "MAX_STREAM_EVENT_BYTES",
    "OperationEventLog",
    "ReplayCursor",
    "STREAM_SCHEMA_VERSION",
    "StreamBackpressureError",
    "StreamContractError",
    "StreamDuplicateConflictError",
    "StreamEvent",
    "StreamReplayGapError",
    "StreamTerminalError",
    "TERMINAL_EVENT_TYPES",
]
