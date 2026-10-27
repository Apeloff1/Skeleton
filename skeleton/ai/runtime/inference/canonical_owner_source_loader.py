"""Owner-backed, fail-closed source reloading for guarded local inference.

The bound conversation ID is supplied by trusted application dispatch, NOT
the provider request. It is never inferred from a compiled handoff. This
loader reads the existing MongoConversationAuthority's current active lineage
and, when enabled, MongoMemoryRepository's active subject records. No archive,
provider transcript, supplied source_snapshot or model output is an authority.

Mixed-owner mode REQUIRES an independent monotonic epoch fence maintained by
the application's mutation paths. Reads alone cannot manufacture an atomic
snapshot across two stores: deployments without that writer protocol must not
enable mixed-owner mode. Other source classes (tools, retrieval, skills,
artifacts, policies) require their own canonical adapters and must not be
silently represented by the conversation/memory inventory.
"""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Protocol

from skeleton.context.sources.conversation import conversation_message_segment
from skeleton.context.sources.memory import memory_record_segment
from skeleton.contracts.conversation import ConversationThreadState
from skeleton.context.sealed_sandwich import (
    SealedContextBoundaryError, SealedContextIntegrityError, SealedContextLimitError,
)
from .canonical_source_custody import CurrentSourceCollection

_MAX_ITEMS = 2000
_MAX_BYTES = 16 * 1024 * 1024


class SharedSourceEpoch(Protocol):
    """Operator-governed epoch advanced by EVERY relevant canonical write.

    This protocol only verifies reads. Its implementer must provide the
    cross-owner commit/visibility invariant; an arbitrary callback, constant
    counter or in-process mutex does NOT constitute a durable writer fence.
    """

    async def read_epoch(
        self, *, tenant_id: str, actor_id: str, context_id: str,
    ) -> int: ...


def _identity(thread: Any, *, tenant_id: str, actor_id: str, thread_id: str) -> tuple:
    if (
        thread.thread_id != thread_id
        or thread.tenant_id != tenant_id
        or thread.owner_id != actor_id
        or thread.state != ConversationThreadState.ACTIVE
        or type(thread.version) is not int or thread.version < 1
        or type(thread.message_sequence) is not int or thread.message_sequence < 1
        or not isinstance(thread.active_branch_id, str)
        or not thread.active_branch_id
    ):
        raise SealedContextBoundaryError("canonical conversation scope or lifecycle revoked")
    return (thread.version, thread.message_sequence, thread.active_branch_id)


class CanonicalOwnerSourceCollectionLoader:
    """Rebuild all configured context candidates from their actual owners.

    A trusted dispatch binds the exact actor, tenant, context and conversation
    thread. A second full read detects in-flight edits and owner-version drift;
    the existing engine bridge ALSO rereads this loader on postflight. For a
    multi-owner deployment the writer-maintained shared epoch is mandatory.
    Unsupported source types fail downstream snapshot-equality admission.
    """

    def __init__(
        self, *, conversation: Any, tenant_id: str, actor_id: str,
        context_id: str, thread_id: str, purpose: str = "model-inference",
        memory: Any | None = None, memory_namespace: str | None = None,
        shared_epoch: SharedSourceEpoch | None = None,
    ) -> None:
        for value in (tenant_id, actor_id, context_id, thread_id, purpose):
            if (not isinstance(value, str) or not value or value != value.strip()
                    or len(value.encode("utf-8", "strict")) > 512):
                raise SealedContextBoundaryError("trusted source owner binding invalid")
        if (not callable(getattr(conversation, "get_thread", None))
                or not callable(getattr(conversation, "active_transcript", None))):
            raise SealedContextBoundaryError("canonical conversation authority required")
        if memory is not None:
            if (not isinstance(memory_namespace, str) or not memory_namespace
                    or not callable(getattr(memory, "list_subject", None))
                    or not callable(getattr(shared_epoch, "read_epoch", None))):
                raise SealedContextBoundaryError(
                    "memory owner requires namespace and shared writer epoch"
                )
        elif memory_namespace is not None or shared_epoch is not None:
            raise SealedContextBoundaryError("unused memory or cross-owner fence")
        self._conversation = conversation
        self._memory = memory
        self._memory_namespace = memory_namespace
        self._epoch = shared_epoch
        self._tenant_id = tenant_id
        self._actor_id = actor_id
        self._context_id = context_id
        self._thread_id = thread_id
        self._purpose = purpose

    async def _epoch_read(self) -> int | None:
        if self._epoch is None:
            return None
        epoch = await self._epoch.read_epoch(
            tenant_id=self._tenant_id, actor_id=self._actor_id,
            context_id=self._context_id,
        )
        if type(epoch) is not int or epoch < 1:
            raise SealedContextBoundaryError("shared canonical owner epoch unavailable")
        return epoch

    async def _read_once(self) -> tuple[tuple, tuple]:
        scope = dict(tenant_id=self._tenant_id, owner_id=self._actor_id)
        thread = await self._conversation.get_thread(self._thread_id, **scope)
        before = _identity(
            thread, tenant_id=self._tenant_id,
            actor_id=self._actor_id, thread_id=self._thread_id,
        )
        messages = await self._conversation.active_transcript(self._thread_id, **scope)
        if not isinstance(messages, tuple) or not 1 <= len(messages) <= _MAX_ITEMS:
            raise SealedContextLimitError("canonical conversation inventory incomplete or unbounded")
        segments = []
        previous_sequence = 0
        for message in messages:
            if (message.thread_id != self._thread_id
                    or type(message.sequence) is not int
                    or message.sequence <= previous_sequence
                    or message.sequence > before[1]):
                raise SealedContextIntegrityError("canonical conversation lineage invalid")
            previous_sequence = message.sequence
            segments.append(conversation_message_segment(
                thread, message, purpose=self._purpose,
            ))
        revisions: list[tuple[str, int]] = []
        if self._memory is not None:
            records = await self._memory.list_subject(
                tenant_id=self._tenant_id, namespace=self._memory_namespace,
                subject_id=self._actor_id, include_tombstoned=False,
            )
            if not isinstance(records, tuple) or len(records) + len(segments) > _MAX_ITEMS:
                raise SealedContextLimitError("canonical memory inventory incomplete or unbounded")
            for record in records:
                if (record.tenant_id != self._tenant_id
                        or record.namespace != self._memory_namespace
                        or record.subject_id != self._actor_id
                        or type(record.version) is not int or record.version < 1):
                    raise SealedContextBoundaryError("canonical memory scope or revision invalid")
                revisions.append((record.memory_id, record.version))
                segments.append(memory_record_segment(
                    record, tenant_id=self._tenant_id, purpose=self._purpose,
                ))
        after_thread = await self._conversation.get_thread(self._thread_id, **scope)
        after = _identity(
            after_thread, tenant_id=self._tenant_id,
            actor_id=self._actor_id, thread_id=self._thread_id,
        )
        if after != before:
            raise SealedContextIntegrityError("conversation owner changed during source load")
        if len(segments) > _MAX_ITEMS or len({
            segment.segment_id for segment in segments
        }) != len(segments):
            raise SealedContextIntegrityError("canonical source identities are incomplete or duplicated")
        total = 0
        for segment in segments:
            if segment.content is None:
                raise SealedContextBoundaryError("canonical source plaintext unavailable")
            body = segment.content.encode("utf-8", "strict")
            if len(body) > 4 * 1024 * 1024:
                raise SealedContextLimitError("canonical candidate is too large")
            total += len(body)
            if total > _MAX_BYTES:
                raise SealedContextLimitError("canonical source inventory exceeds byte budget")
        # Compare detached scalar identities, not mutable owner objects.
        identity = (before, tuple(sorted(revisions)), tuple(sorted(
            (s.segment_id, s.content_digest) for s in segments
        )))
        return identity, tuple(segments)

    async def read_current(
        self, *, tenant_id: str, actor_id: str, context_id: str,
    ) -> CurrentSourceCollection:
        if (tenant_id, actor_id, context_id) != (
            self._tenant_id, self._actor_id, self._context_id,
        ):
            raise SealedContextBoundaryError("canonical source scope is not dispatched owner scope")
        try:
            epoch_before = await self._epoch_read()
            first_identity, first_segments = await self._read_once()
            second_identity, second_segments = await self._read_once()
            epoch_after = await self._epoch_read()
        except (SealedContextBoundaryError, SealedContextIntegrityError,
                SealedContextLimitError):
            raise
        except Exception as exc:
            raise SealedContextBoundaryError("canonical source owners unavailable") from exc
        if first_identity != second_identity or epoch_before != epoch_after:
            raise SealedContextIntegrityError("canonical source owner revisions diverged")
        material = json.dumps(
            [epoch_after, second_identity],
            separators=(",", ":"), ensure_ascii=True, allow_nan=False,
        ).encode("ascii")
        version = int.from_bytes(sha256(material).digest()[:16], "big") or 1
        return CurrentSourceCollection(
            tenant_id=tenant_id, actor_id=actor_id, context_id=context_id,
            version=version, segments=second_segments,
        )


__all__ = ["CanonicalOwnerSourceCollectionLoader", "SharedSourceEpoch"]
