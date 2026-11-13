"""Production execution-to-conversation owner binding, no shadow mapping DB."""

from types import SimpleNamespace

import pytest

from skeleton.context.sealed_sandwich import SealedContextBoundaryError
from skeleton.contracts.conversation import ConversationThreadState
from skeleton.persistence.mongo_execution_source_binding import (
    MongoExecutionConversationResolver,
)
from skeleton.testing.test_engine_submission_snapshot import (
    owner as durable_owner, EXECUTION, TENANT, CONTEXT,
)

ACTOR = "actor"
THREAD = "00000000-0000-4000-8000-000000000099"
TURN = "00000000-0000-4000-8000-000000000098"


class Messages:
    def __init__(self):
        self.document = {"_id": TURN, "author_type": "user", "thread_id": THREAD}
        self.calls = 0

    async def find_one(self, query):
        self.calls += 1
        assert query == {"_id": TURN, "author_type": "user"}
        return self.document


class Conversation:
    def __init__(self, expected):
        self.expected = expected
        self.messages = Messages()
        self.state = ConversationThreadState.ACTIVE
        self.thread_id = THREAD
        self.canonical_command = expected
        self.calls = 0

    async def get_thread(self, thread_id, *, tenant_id, owner_id):
        self.calls += 1
        assert (thread_id, tenant_id, owner_id) == (THREAD, TENANT, ACTOR)
        return SimpleNamespace(state=self.state, thread_id=self.thread_id)

    async def user_engine_command(self, thread_id, turn_id, *, tenant_id, owner_id):
        self.calls += 1
        assert (thread_id, turn_id, tenant_id, owner_id) == (THREAD, TURN, TENANT, ACTOR)
        return self.canonical_command


def setup():
    durable = durable_owner()
    durable.submissions.stored.command.compiled_context.turn_id = TURN
    durable.submissions.stored.command.as_dict = lambda: {"trusted": "command"}
    conversation = Conversation({"trusted": "command"})
    resolver = MongoExecutionConversationResolver(
        conversation=conversation, engine_service=durable,
    )
    return resolver, durable, conversation


async def resolve(resolver):
    return await resolver.resolve(
        execution_id=EXECUTION, tenant_id=TENANT, actor_id=ACTOR,
        context_id=CONTEXT,
    )


@pytest.mark.asyncio
async def test_resolver_binds_real_durable_engine_to_existing_user_command():
    resolver, _, conversation = setup()
    result = await resolve(resolver)
    assert result.execution_id == EXECUTION and result.thread_id == THREAD
    assert result.context_id == CONTEXT
    assert conversation.calls == 2 and conversation.messages.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("alter", (
    "missing_message", "thread_deleted", "wrong_thread",
    "different_command", "missing_command", "engine_cancelled",
    "engine_terminal", "different_actor", "different_handoff",
))
async def test_resolver_denies_deletion_mutation_or_cross_owner_mismatch(alter):
    resolver, durable, conversation = setup()
    if alter == "missing_message":
        conversation.messages.document = None
    elif alter == "thread_deleted":
        conversation.state = ConversationThreadState.DELETING
    elif alter == "wrong_thread":
        conversation.thread_id = "foreign"
    elif alter == "different_command":
        conversation.canonical_command = {"trusted": "other"}
    elif alter == "missing_command":
        conversation.canonical_command = None
    elif alter == "engine_cancelled":
        durable.repository.execution.cancellation_requested = True
    elif alter == "engine_terminal":
        durable.repository.execution.terminal = True
    elif alter == "different_actor":
        durable.submissions.stored.command.operation.actor_id = "foreign"
    else:
        durable.submissions.stored.command.compiled_context.context_id = "foreign"
    with pytest.raises(SealedContextBoundaryError):
        await resolve(resolver)


@pytest.mark.asyncio
async def test_canonical_binding_reads_live_owner_again_not_cached_mapping():
    resolver, durable, conversation = setup()
    assert (await resolve(resolver)).thread_id == THREAD
    conversation.canonical_command = {"trusted": "replaced"}
    with pytest.raises(SealedContextBoundaryError):
        await resolve(resolver)
    assert conversation.messages.calls == 2


def test_production_resolver_requires_both_actual_owner_interfaces():
    with pytest.raises(SealedContextBoundaryError):
        MongoExecutionConversationResolver(conversation=object(), engine_service=object())
