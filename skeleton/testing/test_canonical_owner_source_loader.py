"""Real canonical-owner loader: scope, revision, outage and mixed-owner fencing."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
from types import SimpleNamespace
from uuid import UUID

import pytest

from skeleton.ai.runtime.inference.canonical_owner_source_loader import (
    CanonicalOwnerSourceCollectionLoader,
)
from skeleton.ai.runtime.inference.canonical_source_custody import (
    CanonicalSegmentSourceAuthority,
)
from skeleton.context.sealed_sandwich import (
    SealedContextBoundaryError, SealedContextIntegrityError,
)
from skeleton.contracts.conversation import ConversationAuthorType, ConversationThreadState


TENANT = "tenant"
ACTOR = "actor"
CONTEXT = "00000000-0000-4000-8000-000000000001"
THREAD = str(UUID(int=301))
BRANCH = str(UUID(int=302))


def message(number: int = 1, body: str = "canonical payload"):
    return SimpleNamespace(
        thread_id=THREAD, message_id=str(UUID(int=400 + number)),
        branch_id=BRANCH, sequence=number,
        author_type=ConversationAuthorType.USER,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        content=body, content_ref=None, data_class="confidential",
        operation_id=None, ai_result_id=None, attachment_refs=(),
        tool_receipt_refs=(), citation_refs=(), artifact_refs=(),
    )


class Conversation:
    def __init__(self):
        self.version = 7
        self.state = ConversationThreadState.ACTIVE
        self.owner_id = ACTOR
        self.messages = (message(),)
        self.calls = 0
        self.mutate_on_call = None
        self.unavailable = False

    async def get_thread(self, thread_id, *, tenant_id, owner_id):
        self.calls += 1
        if self.unavailable:
            raise ConnectionError("private credentials and location")
        if self.mutate_on_call == self.calls:
            self.version += 1
        assert (thread_id, tenant_id, owner_id) == (THREAD, TENANT, ACTOR)
        return SimpleNamespace(
            thread_id=THREAD, tenant_id=TENANT, owner_id=self.owner_id,
            state=self.state, version=self.version,
            message_sequence=self.messages[-1].sequence,
            active_branch_id=BRANCH,
        )

    async def active_transcript(self, thread_id, *, tenant_id, owner_id):
        assert (thread_id, tenant_id, owner_id) == (THREAD, TENANT, ACTOR)
        return self.messages


class Memory:
    def __init__(self):
        self.calls = 0
        self.records = ()

    async def list_subject(self, *, tenant_id, namespace, subject_id, include_tombstoned):
        assert (tenant_id, namespace, subject_id, include_tombstoned) == (
            TENANT, "memory", ACTOR, False,
        )
        self.calls += 1
        return self.records


class Epoch:
    def __init__(self):
        self.counter = 10
        self.calls = 0
        self.change_after_first = False

    async def read_epoch(self, *, tenant_id, actor_id, context_id):
        assert (tenant_id, actor_id, context_id) == (TENANT, ACTOR, CONTEXT)
        self.calls += 1
        if self.change_after_first and self.calls > 1:
            self.counter += 1
        return self.counter


def loader(conversation=None, **kwargs):
    return CanonicalOwnerSourceCollectionLoader(
        conversation=conversation or Conversation(),
        tenant_id=TENANT, actor_id=ACTOR, context_id=CONTEXT,
        thread_id=THREAD, **kwargs,
    )


@pytest.mark.asyncio
async def test_actual_conversation_owner_rebuilds_source_bytes_and_rechecks_versions():
    owner = Conversation()
    authority = CanonicalSegmentSourceAuthority(loader=loader(owner))
    current = await authority.inspect(
        tenant_id=TENANT, actor_id=ACTOR, context_id=CONTEXT,
    )
    assert len(current.source_snapshot) == 1
    assert current.source_snapshot[0][1] == sha256(b"canonical payload").hexdigest()
    assert owner.calls == 4
    owner.messages = (message(body="content edited"),)
    owner.version += 1
    later = await authority.inspect(
        tenant_id=TENANT, actor_id=ACTOR, context_id=CONTEXT,
    )
    assert later.source_snapshot != current.source_snapshot
    assert later.version != current.version


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", [
    {"tenant_id": "foreign", "actor_id": ACTOR, "context_id": CONTEXT},
    {"tenant_id": TENANT, "actor_id": "foreign", "context_id": CONTEXT},
    {"tenant_id": TENANT, "actor_id": ACTOR, "context_id": "foreign"},
])
async def test_rejects_unbound_identity(scope):
    with pytest.raises(SealedContextBoundaryError, match="scope"):
        await loader().read_current(**scope)


@pytest.mark.asyncio
async def test_revocation_and_owner_takeover_deny_inference():
    owner = Conversation()
    for field, replacement in (
        ("state", ConversationThreadState.DELETING),
        ("owner_id", "foreign"),
    ):
        original = getattr(owner, field)
        setattr(owner, field, replacement)
        with pytest.raises(SealedContextBoundaryError):
            await loader(owner).read_current(
                tenant_id=TENANT, actor_id=ACTOR, context_id=CONTEXT,
            )
        setattr(owner, field, original)


@pytest.mark.asyncio
async def test_concurrent_writer_during_second_owner_read_denied():
    owner = Conversation()
    owner.mutate_on_call = 3
    with pytest.raises(SealedContextIntegrityError, match="revisions diverged"):
        await loader(owner).read_current(
            tenant_id=TENANT, actor_id=ACTOR, context_id=CONTEXT,
        )


@pytest.mark.asyncio
async def test_missing_owner_or_unavailable_state_is_never_treated_as_empty():
    with pytest.raises(SealedContextBoundaryError):
        loader(object())
    owner = Conversation()
    owner.unavailable = True
    with pytest.raises(SealedContextBoundaryError, match="unavailable") as error:
        await loader(owner).read_current(
            tenant_id=TENANT, actor_id=ACTOR, context_id=CONTEXT,
        )
    assert "private credentials" not in str(error.value)


def test_mixed_owner_requires_independent_writer_epoch():
    with pytest.raises(SealedContextBoundaryError, match="shared writer epoch"):
        loader(memory=Memory(), memory_namespace="memory")
    with pytest.raises(SealedContextBoundaryError):
        loader(memory=Memory(), memory_namespace="memory", shared_epoch=object())


@pytest.mark.asyncio
async def test_cross_owner_epoch_and_full_inventory_are_rechecked_twice():
    owner = Conversation()
    memory = Memory()
    epoch = Epoch()
    instance = loader(
        owner, memory=memory, memory_namespace="memory", shared_epoch=epoch,
    )
    first = await instance.read_current(
        tenant_id=TENANT, actor_id=ACTOR, context_id=CONTEXT,
    )
    assert first.version > 0
    assert memory.calls == 2 and epoch.calls == 2
    epoch.change_after_first = True
    with pytest.raises(SealedContextIntegrityError, match="revisions diverged"):
        await instance.read_current(
            tenant_id=TENANT, actor_id=ACTOR, context_id=CONTEXT,
        )


@pytest.mark.asyncio
async def test_malformed_or_duplicate_live_messages_rejected():
    owner = Conversation()
    owner.messages = (message(1, "first"), message(1, "duplicate"))
    with pytest.raises(SealedContextIntegrityError, match="lineage"):
        await loader(owner).read_current(
            tenant_id=TENANT, actor_id=ACTOR, context_id=CONTEXT,
        )


@pytest.mark.asyncio
async def test_real_owner_inventory_must_match_durable_engine_handoff():
    from skeleton.ai.runtime.inference.engine_submission_snapshot import (
        EngineSubmissionCompiledInputLoader,
    )
    from skeleton.testing.test_engine_submission_snapshot import (
        owner as durable_owner, EXECUTION, REQUEST,
    )

    durable = durable_owner()
    conversation = Conversation()
    authority = CanonicalSegmentSourceAuthority(loader=loader(conversation))
    live = await authority.inspect(
        tenant_id=TENANT, actor_id=ACTOR, context_id=CONTEXT,
    )
    durable.submissions.stored.command.compiled_context.source_snapshot = live.source_snapshot
    bridge = EngineSubmissionCompiledInputLoader(
        service=durable, execution_id=EXECUTION, native_request_digest=REQUEST,
        source_authority=authority,
    )
    assert (await bridge.read(
        tenant_id=TENANT, context_id=CONTEXT, request_digest=REQUEST,
    )).source_version > 0
    conversation.messages = (message(body="new live owner text"),)
    conversation.version += 1
    with pytest.raises(SealedContextIntegrityError, match="custody"):
        await bridge.read(
            tenant_id=TENANT, context_id=CONTEXT, request_digest=REQUEST,
        )
