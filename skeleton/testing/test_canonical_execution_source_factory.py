"""Application-scoped execution source factory enforces exact owner identity."""

from dataclasses import replace

import pytest

from skeleton.ai.runtime.inference.canonical_execution_source_factory import (
    AuthorizedExecutionConversation, CanonicalExecutionSourceFactory,
)
from skeleton.ai.runtime.inference.engine_submission_snapshot import (
    EngineSubmissionCompiledInputLoader,
)
from skeleton.context.sealed_sandwich import (
    SealedContextBoundaryError, SealedContextIntegrityError,
)
from skeleton.testing.test_canonical_owner_source_loader import (
    Conversation, TENANT, ACTOR, CONTEXT, THREAD,
)
from skeleton.testing.test_engine_submission_snapshot import (
    owner as durable_owner, EXECUTION, REQUEST,
)


class Resolver:
    def __init__(self):
        self.calls = 0
        self.binding = AuthorizedExecutionConversation(
            EXECUTION, TENANT, ACTOR, CONTEXT, THREAD,
        )

    async def resolve(self, *, execution_id, tenant_id, actor_id, context_id):
        self.calls += 1
        assert (execution_id, tenant_id, actor_id, context_id) == (
            EXECUTION, TENANT, ACTOR, CONTEXT,
        )
        return self.binding


@pytest.mark.asyncio
async def test_live_execution_binding_reloads_owner_on_every_guarded_read():
    resolver = Resolver()
    conversation = Conversation()
    factory = CanonicalExecutionSourceFactory(
        conversation=conversation, resolver=resolver,
    )
    authority = factory.bind_execution(EXECUTION)
    custody = await authority.inspect(
        tenant_id=TENANT, actor_id=ACTOR, context_id=CONTEXT,
    )
    assert resolver.calls == 1
    durable = durable_owner()
    durable.submissions.stored.command.compiled_context.source_snapshot = custody.source_snapshot
    reader = EngineSubmissionCompiledInputLoader(
        service=durable, execution_id=EXECUTION,
        native_request_digest=REQUEST, source_authority=authority,
    )
    assert (await reader.read(
        tenant_id=TENANT, context_id=CONTEXT, request_digest=REQUEST,
    )).source_version > 0
    assert resolver.calls == 3
    conversation.messages = tuple(
        replace(msg, content="changed", content_ref=None)
        for msg in conversation.messages
    )
    conversation.version += 1
    with pytest.raises(SealedContextIntegrityError, match="custody"):
        await reader.read(
            tenant_id=TENANT, context_id=CONTEXT, request_digest=REQUEST,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("mutate", (
    {"execution_id": "different"}, {"actor_id": "neighbor"},
    {"tenant_id": "neighbor"}, {"context_id": "neighbor"},
    {"thread_id": ""}, {"revoked": True},
))
async def test_forged_or_revoked_persisted_binding_denies_inference(mutate):
    resolver = Resolver()
    resolver.binding = replace(resolver.binding, **mutate)
    factory = CanonicalExecutionSourceFactory(
        conversation=Conversation(), resolver=resolver,
    )
    with pytest.raises(SealedContextBoundaryError):
        await factory.bind_execution(EXECUTION).inspect(
            tenant_id=TENANT, actor_id=ACTOR, context_id=CONTEXT,
        )


@pytest.mark.asyncio
async def test_execution_binding_resolver_outage_is_fail_closed():
    class Outage:
        async def resolve(self, **kwargs):
            raise ConnectionError("secrets that must not enter the log")

    factory = CanonicalExecutionSourceFactory(
        conversation=Conversation(), resolver=Outage(),
    )
    with pytest.raises(SealedContextBoundaryError, match="unavailable") as error:
        await factory.bind_execution(EXECUTION).inspect(
            tenant_id=TENANT, actor_id=ACTOR, context_id=CONTEXT,
        )
    assert "secrets that" not in str(error.value)


def test_no_caller_defined_execution_authority():
    factory = CanonicalExecutionSourceFactory(
        conversation=Conversation(), resolver=Resolver(),
    )
    for invalid in ("", "  ", "bad ", None):
        with pytest.raises(SealedContextBoundaryError):
            factory.bind_execution(invalid)
