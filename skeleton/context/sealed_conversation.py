"""Read-only bridge from authoritative conversation history to encrypted frames.

The existing conversation repository remains the owner of all messages. This
module intentionally does NOT create an independent conversation database or
trust a client-returned archive head. A production durable-outbox/CAS binding
is needed before accepting these frames as an independent recovery authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Protocol

from skeleton.context.sealed_events import ContextEvent, restore_events, seal_event
from skeleton.context.sealed_sandwich import (
    ContextBinding,
    ContextHead,
    ContextSandwichCodec,
    SealedContextBoundaryError,
    SealedContextError,
    SealedContextReplayError,
)


class ConversationHistoryReader(Protocol):
    """Canonical tenant-authorized conversation API (SQLite reference shape)."""

    def get_thread(self, thread_id: str, *, tenant_id: str, owner_id: str) -> Any: ...

    def list_messages(
        self, thread_id: str, *, tenant_id: str, owner_id: str,
        after_sequence: int = 0, limit: int = 500,
    ) -> tuple[Any, ...]: ...


@dataclass(frozen=True, slots=True)
class SealedConversationExport:
    """Encrypted candidate export, not yet a transactionally committed archive."""

    envelopes: tuple[bytes, ...]
    head: ContextHead
    thread_version: int
    message_count: int


def _json_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def canonical_history_events(
    reader: ConversationHistoryReader, *, binding: ContextBinding
) -> tuple[tuple[ContextEvent, ...], int]:
    """Reconstruct ALL messages, including alternate-branch history, in pages.

    Content_ref and attachment_refs are preserved *verbatim as references*;
    their externally held object bytes require independent archival export.
    """
    thread = reader.get_thread(
        binding.conversation_id, tenant_id=binding.tenant_id, owner_id=binding.owner_id
    )
    if thread.thread_id != binding.conversation_id:
        raise SealedContextBoundaryError("conversation reader returned a mismatched thread")
    expected_version = thread.version
    expected_sequence = thread.message_sequence
    result: list[ContextEvent] = [
        ContextEvent("thread:" + thread.thread_id, "checkpoint", _json_bytes(thread.as_dict()))
    ]
    cursor = 0
    while cursor < expected_sequence:
        page = reader.list_messages(
            binding.conversation_id,
            tenant_id=binding.tenant_id,
            owner_id=binding.owner_id,
            after_sequence=cursor,
            limit=500,
        )
        if not page:
            raise SealedContextReplayError("canonical conversation message page is missing")
        for message in page:
            if message.thread_id != binding.conversation_id or type(message.sequence) is not int:
                raise SealedContextBoundaryError("conversation message crossed identity boundary")
            if message.sequence != cursor + 1 or message.sequence > expected_sequence:
                raise SealedContextReplayError("canonical message sequence is incomplete")
            cursor = message.sequence
            author = str(message.author_type.value)
            kind = author if author in {"user", "assistant", "tool"} else "evidence"
            result.append(ContextEvent(message.message_id, kind, _json_bytes(message.as_dict())))
    latest = reader.get_thread(
        binding.conversation_id, tenant_id=binding.tenant_id, owner_id=binding.owner_id
    )
    if latest.version != expected_version or latest.as_dict() != thread.as_dict():
        raise SealedContextReplayError("conversation changed while preparing encrypted archive")
    return tuple(result), expected_version


def export_canonical_conversation(
    reader: ConversationHistoryReader,
    codec: ContextSandwichCodec,
    *,
    binding: ContextBinding,
) -> SealedConversationExport:
    """Create sealed pages from a stable canonical repository snapshot.

    The resulting head must be independently committed alongside the archive
    publication. Until that exists, replay against the canonical repository.
    """
    events, version = canonical_history_events(reader, binding=binding)
    head = ContextHead()
    frames: list[bytes] = []
    for event in events:
        wire, head = seal_event(codec, event, binding=binding, previous=head)
        frames.append(wire)
    return SealedConversationExport(tuple(frames), head, version, len(events) - 1)


def verify_export_against_canonical_conversation(
    reader: ConversationHistoryReader,
    codec: ContextSandwichCodec,
    exported: SealedConversationExport,
    *,
    binding: ContextBinding,
) -> None:
    """Use server-side canonical conversation, NOT client head, as authority.

    Catch valid-but-stale archives even when clients return their matching old
    envelope/head pair. This is a read-only verification; it is not a CAS write.
    """
    if not isinstance(exported, SealedConversationExport):
        raise SealedContextError("invalid encrypted conversation export")
    actual, version = canonical_history_events(reader, binding=binding)
    restored = restore_events(codec, exported.envelopes, binding=binding, trusted_head=exported.head)
    if version != exported.thread_version or exported.message_count != len(actual) - 1:
        raise SealedContextReplayError("encrypted export does not match canonical conversation version")
    if len(actual) != len(restored) or any(
        left != right for left, right in zip(actual, restored)
    ):
        raise SealedContextReplayError("encrypted export does not match canonical conversation bytes")
