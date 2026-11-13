"""Lossless event payloads and explicit archival/context-window separation.

This module does not promote serialized roles to runtime authority: restoring a
'system' event cannot bypass policy admission at skeleton.context.compiler.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import json
from typing import Iterable

from skeleton.context.sealed_sandwich import (
    ContextBinding,
    ContextHead,
    ContextSandwichCodec,
    SealedContextError,
    SealedContextLimitError,
)

EVENT_SCHEMA_VERSION = 1
_EVENT_KINDS = frozenset(
    {"system", "developer", "user", "assistant", "tool", "evidence", "receipt", "checkpoint"}
)
_MAX_EVENT_BYTES = 3 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ContextEvent:
    """Original byte payload and provenance, without any lossy text coercion."""

    event_id: str
    kind: str
    content: bytes
    source_ref: str = "application"

    def __post_init__(self) -> None:
        for label in ("event_id", "source_ref"):
            value = getattr(self, label)
            if not isinstance(value, str) or not 1 <= len(value) <= 256 or value != value.strip():
                raise SealedContextError(f"invalid {label}")
        if self.kind not in _EVENT_KINDS:
            raise SealedContextError("unsupported event classification")
        if not isinstance(self.content, bytes) or len(self.content) > _MAX_EVENT_BYTES:
            raise SealedContextLimitError("event payload exceeds bounded event size")


def encode_event(event: ContextEvent) -> bytes:
    """Deterministically encode an exact byte payload (including NUL/Unicode)."""
    if not isinstance(event, ContextEvent):
        raise SealedContextError("ContextEvent required")
    value = {
        "schema_version": EVENT_SCHEMA_VERSION,
        "event_id": event.event_id,
        "kind": event.kind,
        "source_ref": event.source_ref,
        "content_base64": base64.urlsafe_b64encode(event.content).decode("ascii"),
    }
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def decode_event(payload: bytes) -> ContextEvent:
    if not isinstance(payload, bytes) or len(payload) > 4 * 1024 * 1024:
        raise SealedContextLimitError("encoded event exceeds bounded event size")
    try:
        value = json.loads(payload)
        if type(value) is not dict or set(value) != {
            "schema_version", "event_id", "kind", "source_ref", "content_base64"
        } or type(value["schema_version"]) is not int or value["schema_version"] != EVENT_SCHEMA_VERSION:
            raise ValueError("invalid event schema")
        raw = value["content_base64"]
        if not isinstance(raw, str) or len(raw) > (_MAX_EVENT_BYTES * 4 // 3 + 8):
            raise ValueError("invalid event payload")
        content = base64.b64decode(raw, altchars=b"-_", validate=True)
        if base64.urlsafe_b64encode(content).decode("ascii") != raw:
            raise ValueError("noncanonical event payload")
        event = ContextEvent(value["event_id"], value["kind"], content, value["source_ref"])
        if encode_event(event) != payload:
            raise ValueError("noncanonical event wire")
        return event
    except (ValueError, TypeError, KeyError, UnicodeDecodeError, binascii.Error) as exc:
        raise SealedContextError("invalid archival context event") from exc


def seal_event(
    codec: ContextSandwichCodec,
    event: ContextEvent,
    *,
    binding: ContextBinding,
    previous: ContextHead,
) -> tuple[bytes, ContextHead]:
    """Produce a candidate; persist with a trusted CAS head transaction."""
    return codec.seal(encode_event(event), binding=binding, previous=previous)


def restore_events(
    codec: ContextSandwichCodec,
    envelopes: Iterable[bytes],
    *,
    binding: ContextBinding,
    trusted_head: ContextHead,
    starting_head: ContextHead = ContextHead(),
) -> tuple[ContextEvent, ...]:
    frames = codec.replay(
        envelopes, binding=binding, trusted_head=trusted_head, starting_head=starting_head
    )
    events = tuple(decode_event(frame.payload) for frame in frames)
    if len({event.event_id for event in events}) != len(events):
        raise SealedContextError("archived context contains duplicate event IDs")
    return events


def require_model_window(
    events: Iterable[ContextEvent], *, max_input_bytes: int
) -> tuple[ContextEvent, ...]:
    """Fail rather than silently truncate; provider/tokenizer admission follows.

    A byte cap is NOT a token-window guarantee. The canonical context compiler
    must still apply tokenizer, instructions, trust, and output reservations.
    """
    if type(max_input_bytes) is not int or max_input_bytes < 0:
        raise ValueError("max_input_bytes must be a nonnegative integer")
    result = tuple(events)
    if sum(len(event.content) for event in result) > max_input_bytes:
        raise SealedContextLimitError("lossless archive exceeds caller's live model byte budget")
    return result
