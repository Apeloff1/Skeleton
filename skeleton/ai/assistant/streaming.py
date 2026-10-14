"""Content-minimized durable streaming projection for AI-chat turns.

The durable turn journal is authoritative. This module projects journal
transitions into reconnectable client events without exposing prompts,
retrieved evidence, hidden reasoning, or arbitrary tool/model payloads.

Reconnect semantics are bound to both sequence and event digest. A client may
resume only from an exact cursor; gaps, cross-operation cursors, and digest
mismatches fail closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .contracts import digest_json
from .turn_runtime import TERMINAL_STATES, TurnEvent, TurnState


CHAT_STREAM_SCHEMA_VERSION = 1


class ChatStreamError(ValueError):
    """A stream projection or reconnect invariant was violated."""


_KIND_BY_STATE: Mapping[TurnState, str] = {
    TurnState.ADMITTED: "turn.accepted",
    TurnState.USER_MESSAGE_COMMITTED: "message.user_committed",
    TurnState.CONTEXT_COMPILING: "context.started",
    TurnState.ROUTING: "routing.started",
    TurnState.MODEL_RUNNING: "model.running",
    TurnState.TOOL_REQUIRED: "tool.proposed",
    TurnState.AWAITING_USER: "tool.approval_required",
    TurnState.TOOL_EXECUTING: "tool.started",
    TurnState.VERIFYING: "verification.started",
    TurnState.FINALIZING: "response.finalizing",
    TurnState.ASSISTANT_MESSAGE_COMMITTED: "message.committed",
    TurnState.MEMORY_PROPOSAL: "memory.proposed",
    TurnState.COMPLETE: "turn.completed",
    TurnState.DEGRADED: "turn.degraded",
    TurnState.FAILED_RETRYABLE: "turn.failed_retryable",
    TurnState.FAILED_TERMINAL: "turn.failed_terminal",
    TurnState.CANCELLED: "turn.cancelled",
    TurnState.QUARANTINED: "turn.quarantined",
}


def _text(value: object, field_name: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ChatStreamError(f"{field_name} must be non-empty text")
    normalized = value.strip()
    if len(normalized) > maximum:
        raise ChatStreamError(f"{field_name} exceeds maximum length")
    return normalized


def _sha256(value: object, field_name: str) -> str:
    text = _text(value, field_name, maximum=64)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ChatStreamError(f"{field_name} must be lowercase sha256")
    return text


@dataclass(frozen=True, slots=True)
class TurnStreamCursor:
    operation_id: str
    last_seen_sequence: int = 0
    last_event_digest: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "operation_id",
            _text(self.operation_id, "operation_id", maximum=256),
        )
        if (
            isinstance(self.last_seen_sequence, bool)
            or not isinstance(self.last_seen_sequence, int)
            or self.last_seen_sequence < 0
        ):
            raise ChatStreamError(
                "last_seen_sequence must be a non-negative integer"
            )
        if self.last_seen_sequence == 0:
            if self.last_event_digest is not None:
                raise ChatStreamError(
                    "zero stream cursor cannot carry an event digest"
                )
        elif self.last_event_digest is None:
            raise ChatStreamError(
                "non-zero stream cursor requires event digest"
            )
        if self.last_event_digest is not None:
            object.__setattr__(
                self,
                "last_event_digest",
                _sha256(
                    self.last_event_digest,
                    "last_event_digest",
                ),
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": CHAT_STREAM_SCHEMA_VERSION,
            "operation_id": self.operation_id,
            "last_seen_sequence": self.last_seen_sequence,
            "last_event_digest": self.last_event_digest,
        }


@dataclass(frozen=True, slots=True)
class TurnStreamEvent:
    operation_id: str
    sequence: int
    event_id: str
    kind: str
    from_state: str
    to_state: str
    observed_at: str
    event_digest: str
    previous_event_digest: str | None
    reason_code: str
    terminal: bool
    tool_receipt_ref: str | None = None
    provider_receipt_ref: str | None = None
    failure_class: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "operation_id",
            _text(self.operation_id, "operation_id", maximum=256),
        )
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 1
        ):
            raise ChatStreamError("sequence must be a positive integer")
        object.__setattr__(
            self,
            "event_id",
            _sha256(self.event_id, "event_id"),
        )
        object.__setattr__(
            self,
            "event_digest",
            _sha256(self.event_digest, "event_digest"),
        )
        if self.previous_event_digest is not None:
            object.__setattr__(
                self,
                "previous_event_digest",
                _sha256(
                    self.previous_event_digest,
                    "previous_event_digest",
                ),
            )
        object.__setattr__(
            self,
            "kind",
            _text(self.kind, "kind", maximum=128),
        )
        object.__setattr__(
            self,
            "from_state",
            _text(self.from_state, "from_state", maximum=64),
        )
        object.__setattr__(
            self,
            "to_state",
            _text(self.to_state, "to_state", maximum=64),
        )
        object.__setattr__(
            self,
            "observed_at",
            _text(self.observed_at, "observed_at", maximum=128),
        )
        object.__setattr__(
            self,
            "reason_code",
            _text(self.reason_code, "reason_code", maximum=128),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": CHAT_STREAM_SCHEMA_VERSION,
            "operation_id": self.operation_id,
            "sequence": self.sequence,
            "event_id": self.event_id,
            "kind": self.kind,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "observed_at": self.observed_at,
            "event_digest": self.event_digest,
            "previous_event_digest": self.previous_event_digest,
            "reason_code": self.reason_code,
            "terminal": self.terminal,
            "tool_receipt_ref": self.tool_receipt_ref,
            "provider_receipt_ref": self.provider_receipt_ref,
            "failure_class": self.failure_class,
        }


@dataclass(frozen=True, slots=True)
class TurnStreamPage:
    operation_id: str
    events: tuple[TurnStreamEvent, ...]
    cursor: TurnStreamCursor
    terminal: bool

    def __post_init__(self) -> None:
        if self.cursor.operation_id != self.operation_id:
            raise ChatStreamError(
                "stream page cursor belongs to a different operation"
            )
        if self.events:
            if self.events[-1].sequence != self.cursor.last_seen_sequence:
                raise ChatStreamError(
                    "stream cursor does not point at the page tail"
                )
            if self.events[-1].event_digest != self.cursor.last_event_digest:
                raise ChatStreamError(
                    "stream cursor digest does not match page tail"
                )

    @property
    def digest(self) -> str:
        return digest_json(
            {
                "schema_version": CHAT_STREAM_SCHEMA_VERSION,
                "operation_id": self.operation_id,
                "events": [event.as_dict() for event in self.events],
                "cursor": self.cursor.as_dict(),
                "terminal": self.terminal,
            }
        )


def project_turn_event(event: TurnEvent) -> TurnStreamEvent:
    """Project one durable event without forwarding arbitrary payload content."""

    if not isinstance(event, TurnEvent):
        raise TypeError("event must be TurnEvent")
    kind = _KIND_BY_STATE.get(event.to_state)
    if kind is None:
        raise ChatStreamError(
            f"turn state has no public stream projection: {event.to_state.value}"
        )
    event_id = digest_json(
        {
            "schema_version": CHAT_STREAM_SCHEMA_VERSION,
            "operation_id": event.operation_id,
            "sequence": event.sequence,
            "event_digest": event.digest,
            "kind": kind,
        }
    )
    return TurnStreamEvent(
        operation_id=event.operation_id,
        sequence=event.sequence,
        event_id=event_id,
        kind=kind,
        from_state=event.from_state.value,
        to_state=event.to_state.value,
        observed_at=event.observed_at.isoformat(),
        event_digest=event.digest,
        previous_event_digest=event.previous_event_digest,
        reason_code=event.reason_code,
        terminal=event.to_state in TERMINAL_STATES,
        tool_receipt_ref=event.tool_receipt_ref,
        provider_receipt_ref=event.provider_receipt_ref,
        failure_class=(
            None
            if event.failure_class is None
            else event.failure_class.value
        ),
    )


def project_turn_page(
    events: Iterable[TurnEvent],
    *,
    cursor: TurnStreamCursor,
    limit: int = 100,
) -> TurnStreamPage:
    """Validate and project the exact journal suffix following the cursor."""

    if not isinstance(cursor, TurnStreamCursor):
        raise TypeError("cursor must be TurnStreamCursor")
    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 1 <= limit <= 1000
    ):
        raise ChatStreamError("limit must be between 1 and 1000")

    raw = tuple(events)
    if not raw:
        return TurnStreamPage(
            operation_id=cursor.operation_id,
            events=(),
            cursor=cursor,
            terminal=False,
        )

    expected_sequence = cursor.last_seen_sequence + 1
    expected_previous = cursor.last_event_digest
    projected: list[TurnStreamEvent] = []

    for event in raw:
        if event.operation_id != cursor.operation_id:
            raise ChatStreamError(
                "stream event belongs to a different operation"
            )
        if event.sequence < expected_sequence:
            continue
        if event.sequence != expected_sequence:
            raise ChatStreamError("stream journal contains a sequence gap")
        if event.previous_event_digest != expected_previous:
            raise ChatStreamError("stream journal digest chain is broken")

        public = project_turn_event(event)
        projected.append(public)
        expected_sequence += 1
        expected_previous = event.digest
        if len(projected) >= limit:
            break

    if not projected:
        return TurnStreamPage(
            operation_id=cursor.operation_id,
            events=(),
            cursor=cursor,
            terminal=False,
        )

    next_cursor = TurnStreamCursor(
        operation_id=cursor.operation_id,
        last_seen_sequence=projected[-1].sequence,
        last_event_digest=projected[-1].event_digest,
    )
    return TurnStreamPage(
        operation_id=cursor.operation_id,
        events=tuple(projected),
        cursor=next_cursor,
        terminal=projected[-1].terminal,
    )


def require_resume_cursor(
    *,
    operation_id: str,
    last_seen_sequence: int,
    last_event_digest: str | None,
) -> TurnStreamCursor:
    """Construct a fail-closed reconnect cursor from client resume fields."""

    return TurnStreamCursor(
        operation_id=operation_id,
        last_seen_sequence=last_seen_sequence,
        last_event_digest=last_event_digest,
    )


__all__ = [
    "CHAT_STREAM_SCHEMA_VERSION",
    "ChatStreamError",
    "TurnStreamCursor",
    "TurnStreamEvent",
    "TurnStreamPage",
    "project_turn_event",
    "project_turn_page",
    "require_resume_cursor",
]
