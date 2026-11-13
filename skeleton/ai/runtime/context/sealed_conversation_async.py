"""Async, bounded-memory Mongo conversation -> sealed context staging bridge.

The canonical Mongo conversation reader remains the authority. A staging sink is
NOT a trusted head store; publication requires a transactionally fenced commit
in the existing conversation owner after this stage returns successfully.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, AsyncIterable, AsyncIterator, Protocol

from skeleton.context.sealed_events import ContextEvent, decode_event, seal_event
from skeleton.context.sealed_sandwich import (
    ContextBinding,
    ContextHead,
    ContextSandwichCodec,
    SealedContextBoundaryError,
    SealedContextError,
    SealedContextLimitError,
    SealedContextReplayError,
)


_MAX_ARCHIVE_FRAMES = 1_000_000
_PAGE_SIZE = 500


class AsyncConversationHistoryReader(Protocol):
    """Read-only contract satisfied by backend.core.conversations.MongoConversationAuthority."""

    async def get_thread(self, thread_id: str, *, tenant_id: str, owner_id: str) -> Any: ...

    async def list_messages(
        self, thread_id: str, *, tenant_id: str, owner_id: str,
        after_sequence: int = 0, limit: int = 500,
    ) -> tuple[Any, ...]: ...


@dataclass(frozen=True, slots=True)
class StagedContextReceipt:
    """Candidate stream metadata; must NEVER be mistaken for a trusted CAS head."""

    head: ContextHead
    thread_version: int
    message_count: int
    ciphertext_bytes: int


class AsyncFrameStagingSink(Protocol):
    """Untrusted transient sink: no authority transfer to client/object storage."""

    async def begin(self, *, binding: ContextBinding, thread_version: int) -> None: ...

    async def append(self, wire: bytes) -> None: ...

    async def complete(self, receipt: StagedContextReceipt) -> None: ...

    async def abort(self) -> None: ...


def _json_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


async def iter_canonical_events_async(
    reader: AsyncConversationHistoryReader, *, binding: ContextBinding,
) -> AsyncIterator[tuple[ContextEvent, int]]:
    """Yield every immutable canonical message (including inactive branches).

    Bound residency to a 500-message page. Validate exact-next sequencing and
    the source snapshot after reading; callers MUST discard staged output if
    iteration raises, including on final version drift.
    """
    thread = await reader.get_thread(
        binding.conversation_id, tenant_id=binding.tenant_id, owner_id=binding.owner_id
    )
    if thread.thread_id != binding.conversation_id:
        raise SealedContextBoundaryError("conversation reader returned the wrong thread")
    version, end_sequence = thread.version, thread.message_sequence
    if type(version) is not int or version < 1 or type(end_sequence) is not int:
        raise SealedContextError("invalid canonical conversation version")
    if not 0 <= end_sequence < _MAX_ARCHIVE_FRAMES:
        raise SealedContextLimitError("conversation exceeds archive frame-count limit")
    yield ContextEvent("thread:" + thread.thread_id, "checkpoint", _json_bytes(thread.as_dict())), version
    cursor = 0
    while cursor < end_sequence:
        page = await reader.list_messages(
            binding.conversation_id, tenant_id=binding.tenant_id, owner_id=binding.owner_id,
            after_sequence=cursor, limit=_PAGE_SIZE,
        )
        if not page or len(page) > _PAGE_SIZE:
            raise SealedContextReplayError("conversation page missing or malformed")
        for message in page:
            if message.thread_id != binding.conversation_id or type(message.sequence) is not int:
                raise SealedContextBoundaryError("canonical message crossed authority boundary")
            if message.sequence != cursor + 1 or message.sequence > end_sequence:
                raise SealedContextReplayError("canonical conversation sequence gap")
            cursor = message.sequence
            author = getattr(message.author_type, "value", None)
            kind = author if author in {"user", "assistant", "tool"} else "evidence"
            yield ContextEvent(message.message_id, kind, _json_bytes(message.as_dict())), version
    latest = await reader.get_thread(
        binding.conversation_id, tenant_id=binding.tenant_id, owner_id=binding.owner_id
    )
    if latest.version != version or latest.as_dict() != thread.as_dict():
        raise SealedContextReplayError("conversation changed during archive staging")


async def stage_canonical_conversation_async(
    reader: AsyncConversationHistoryReader,
    codec: ContextSandwichCodec,
    sink: AsyncFrameStagingSink,
    *,
    binding: ContextBinding,
) -> StagedContextReceipt:
    """Seal a complete conversation into temporary frames, aborting on any error.

    The sink's complete means *staged*, not durably committed. The caller
    must atomically commit frames+trusted head using the existing authority,
    and cannot replace independent conversation history with this output.
    """
    if not isinstance(binding, ContextBinding):
        raise SealedContextBoundaryError("backend-authorized context binding required")
    head = ContextHead()
    version: int | None = None
    total_bytes = 0
    started = False
    try:
        async for event, snapshot_version in iter_canonical_events_async(reader, binding=binding):
            if not started:
                started = True  # abort even if begin partially writes before failing
                await sink.begin(binding=binding, thread_version=snapshot_version)
                version = snapshot_version
            if snapshot_version != version:
                raise SealedContextReplayError("canonical snapshot version drift")
            wire, head = seal_event(codec, event, binding=binding, previous=head)
            await sink.append(wire)
            total_bytes += len(wire)
        if version is None or not started:
            raise SealedContextError("canonical conversation produced no checkpoint")
        receipt = StagedContextReceipt(head, version, head.sequence - 1, total_bytes)
        await sink.complete(receipt)
        return receipt
    except BaseException:
        if started:
            await sink.abort()
        raise


async def verify_staged_conversation_async(
    reader: AsyncConversationHistoryReader,
    codec: ContextSandwichCodec,
    envelopes: AsyncIterable[bytes],
    receipt: StagedContextReceipt,
    *,
    binding: ContextBinding,
) -> None:
    """Verify decrypted archival bytes against independently fetched Mongo state.

    Handles one page/event at a time; refuses stale archives, shortened tails,
    extra events, wrong identity, or a changed canonical snapshot.
    """
    if not isinstance(receipt, StagedContextReceipt):
        raise SealedContextError("invalid staging receipt")
    wire_iter = aiter(envelopes)
    previous = ContextHead()
    ciphertext_bytes = 0
    count = 0
    async for event, thread_version in iter_canonical_events_async(reader, binding=binding):
        try:
            wire = await anext(wire_iter)
        except StopAsyncIteration as exc:
            raise SealedContextReplayError("encrypted archive is missing canonical events") from exc
        frame = codec.open(wire, binding=binding, previous=previous)
        if decode_event(frame.payload) != event:
            raise SealedContextReplayError("encrypted archive mismatches canonical bytes")
        previous = frame.head
        ciphertext_bytes += len(wire)
        count += 1
        if thread_version != receipt.thread_version:
            raise SealedContextReplayError("encrypted archive uses a stale canonical version")
    try:
        await anext(wire_iter)
    except StopAsyncIteration:
        pass
    else:
        raise SealedContextReplayError("encrypted archive has an uncommitted tail")
    if (
        previous != receipt.head
        or count - 1 != receipt.message_count
        or ciphertext_bytes != receipt.ciphertext_bytes
    ):
        raise SealedContextReplayError("archive receipt disagrees with reconstructed evidence")
