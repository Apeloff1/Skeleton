from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from core.chat_turn_lifecycle import ChatTurnLifecycle
from skeleton.ai.assistant.turn_runtime import (
    TurnState,
    provider_receipt_set_ref,
)
from skeleton.contracts.conversation import (
    ConversationAuthorType,
    ConversationMessage,
    ConversationThread,
    ConversationThreadState,
)
from skeleton.persistence.chat_turn_repository import SQLiteChatTurnRepository


NOW = datetime(2026, 10, 6, 3, 0, tzinfo=timezone.utc)
TENANT = "tenant-a"
OWNER = "owner-a"


class AsyncAuthority:
    def __init__(self):
        self.repo = SQLiteChatTurnRepository()

    async def create_operation(self, **kwargs):
        return self.repo.create_operation(**kwargs)

    async def get_operation(self, operation_id, **kwargs):
        return self.repo.get_operation(operation_id, **kwargs)

    async def append_event(self, event, **kwargs):
        return self.repo.append_event(event, **kwargs)


def _thread_and_user():
    thread_id = str(uuid4())
    branch_id = str(uuid4())
    user_id = str(uuid4())
    thread = ConversationThread(
        thread_id=thread_id,
        tenant_id=TENANT,
        owner_id=OWNER,
        created_at=NOW,
        updated_at=NOW,
        version=2,
        message_sequence=1,
        active_branch_id=branch_id,
        state=ConversationThreadState.ACTIVE,
        title="chat",
    )
    user = ConversationMessage(
        message_id=user_id,
        thread_id=thread_id,
        branch_id=branch_id,
        sequence=1,
        author_type=ConversationAuthorType.USER,
        created_at=NOW,
        idempotency_key="turn-1",
        content="hello",
    )
    return thread, user


@pytest.mark.asyncio
async def test_begin_binds_canonical_user_and_commits_first_two_stages():
    lifecycle = ChatTurnLifecycle(AsyncAuthority())
    thread, user = _thread_and_user()
    operation_id = str(uuid4())

    turn = await lifecycle.begin(
        thread=thread,
        user_message=user,
        operation_id=operation_id,
        request_digest="a" * 64,
        tenant_id=TENANT,
        owner_id=OWNER,
    )

    assert turn.snapshot.state is TurnState.USER_MESSAGE_COMMITTED
    assert turn.binding.thread_id == thread.thread_id
    assert turn.binding.causal_user_message_id == user.message_id
    assert turn.snapshot.next_sequence == 3


@pytest.mark.asyncio
async def test_progressed_operation_creation_is_idempotent_on_retry():
    authority = AsyncAuthority()
    lifecycle = ChatTurnLifecycle(authority)
    thread, user = _thread_and_user()
    operation_id = str(uuid4())

    turn = await lifecycle.begin(
        thread=thread,
        user_message=user,
        operation_id=operation_id,
        request_digest="b" * 64,
        tenant_id=TENANT,
        owner_id=OWNER,
    )
    turn = await lifecycle.advance(
        turn,
        TurnState.MODEL_RUNNING,
        tenant_id=TENANT,
        owner_id=OWNER,
        reason_code="first-attempt",
    )

    later_thread = ConversationThread(
        thread_id=thread.thread_id,
        tenant_id=thread.tenant_id,
        owner_id=thread.owner_id,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        version=99,
        message_sequence=7,
        active_branch_id=thread.active_branch_id,
        state=thread.state,
        title=thread.title,
        data_class=thread.data_class,
    )
    retried = await lifecycle.begin(
        thread=later_thread,
        user_message=user,
        operation_id=operation_id,
        request_digest="b" * 64,
        tenant_id=TENANT,
        owner_id=OWNER,
    )
    assert retried.snapshot.state is TurnState.MODEL_RUNNING
    assert retried.snapshot.last_event_digest == turn.snapshot.last_event_digest


@pytest.mark.asyncio
async def test_success_path_advances_to_complete_without_replaying_prior_stages():
    lifecycle = ChatTurnLifecycle(AsyncAuthority())
    thread, user = _thread_and_user()
    turn = await lifecycle.begin(
        thread=thread,
        user_message=user,
        operation_id=str(uuid4()),
        request_digest="c" * 64,
        tenant_id=TENANT,
        owner_id=OWNER,
    )
    turn = await lifecycle.advance(
        turn,
        TurnState.MODEL_RUNNING,
        tenant_id=TENANT,
        owner_id=OWNER,
        reason_code="engine-started",
    )
    turn = await lifecycle.advance(
        turn,
        TurnState.FINALIZING,
        tenant_id=TENANT,
        owner_id=OWNER,
        reason_code="verified-result",
        provider_receipt_ref="provider:test:receipt-1",
    )
    turn = await lifecycle.advance(
        turn,
        TurnState.COMPLETE,
        tenant_id=TENANT,
        owner_id=OWNER,
        reason_code="assistant-committed",
    )
    assert turn.snapshot.state is TurnState.COMPLETE
    assert turn.snapshot.terminal is True


@pytest.mark.asyncio
async def test_retryable_and_cancelled_failures_are_terminal():
    lifecycle = ChatTurnLifecycle(AsyncAuthority())
    thread, user = _thread_and_user()

    retry_turn = await lifecycle.begin(
        thread=thread,
        user_message=user,
        operation_id=str(uuid4()),
        request_digest="d" * 64,
        tenant_id=TENANT,
        owner_id=OWNER,
    )
    retry_turn = await lifecycle.advance(
        retry_turn,
        TurnState.MODEL_RUNNING,
        tenant_id=TENANT,
        owner_id=OWNER,
        reason_code="engine-started",
    )
    retry_turn = await lifecycle.fail(
        retry_turn,
        tenant_id=TENANT,
        owner_id=OWNER,
        reason_code="engine-unavailable",
        retryable=True,
    )
    assert retry_turn.snapshot.state is TurnState.FAILED_RETRYABLE

    thread2, user2 = _thread_and_user()
    cancelled = await lifecycle.begin(
        thread=thread2,
        user_message=user2,
        operation_id=str(uuid4()),
        request_digest="e" * 64,
        tenant_id=TENANT,
        owner_id=OWNER,
    )
    cancelled = await lifecycle.advance(
        cancelled,
        TurnState.MODEL_RUNNING,
        tenant_id=TENANT,
        owner_id=OWNER,
        reason_code="engine-started",
    )
    cancelled = await lifecycle.fail(
        cancelled,
        tenant_id=TENANT,
        owner_id=OWNER,
        reason_code="user-cancelled",
        cancelled=True,
    )
    assert cancelled.snapshot.state is TurnState.CANCELLED


@pytest.mark.asyncio
async def test_provider_receipt_set_binds_all_receipts_and_rejects_drift():
    lifecycle = ChatTurnLifecycle(AsyncAuthority())
    thread, user = _thread_and_user()
    turn = await lifecycle.begin(
        thread=thread,
        user_message=user,
        operation_id=str(uuid4()),
        request_digest="6" * 64,
        tenant_id=TENANT,
        owner_id=OWNER,
    )
    turn = await lifecycle.advance(
        turn,
        TurnState.MODEL_RUNNING,
        tenant_id=TENANT,
        owner_id=OWNER,
        reason_code="engine-started",
    )
    receipts = (
        "provider:test:receipt-2",
        "provider:test:receipt-1",
    )
    turn = await lifecycle.advance(
        turn,
        TurnState.FINALIZING,
        tenant_id=TENANT,
        owner_id=OWNER,
        reason_code="verified-result",
        provider_receipt_refs=receipts,
    )
    events = lifecycle.authority.repo.list_events(
        turn.snapshot.operation_id,
        tenant_id=TENANT,
        owner_id=OWNER,
    )
    bound_events = [
        event
        for event in events
        if event.provider_receipt_ref is not None
    ]
    assert len(bound_events) == 1
    assert bound_events[0].to_state is TurnState.VERIFYING
    assert turn.snapshot.provider_receipt_ref == provider_receipt_set_ref(
        receipts
    )
    assert lifecycle.assert_provider_receipts(
        turn,
        tuple(reversed(receipts)),
    ) == provider_receipt_set_ref(receipts)

    with pytest.raises(ValueError, match="binding drifted"):
        await lifecycle.advance(
            turn,
            TurnState.COMPLETE,
            tenant_id=TENANT,
            owner_id=OWNER,
            reason_code="assistant-committed",
            provider_receipt_refs=(
                "provider:test:receipt-1",
                "provider:test:receipt-3",
            ),
        )


@pytest.mark.asyncio
async def test_legacy_single_provider_receipt_remains_compatible():
    lifecycle = ChatTurnLifecycle(AsyncAuthority())
    thread, user = _thread_and_user()
    turn = await lifecycle.begin(
        thread=thread,
        user_message=user,
        operation_id=str(uuid4()),
        request_digest="7" * 64,
        tenant_id=TENANT,
        owner_id=OWNER,
    )
    turn = await lifecycle.advance(
        turn,
        TurnState.FINALIZING,
        tenant_id=TENANT,
        owner_id=OWNER,
        reason_code="legacy-verified-result",
        provider_receipt_ref="provider:test:legacy-receipt",
    )
    assert lifecycle.assert_provider_receipts(
        turn,
        ("provider:test:legacy-receipt",),
    ) == provider_receipt_set_ref(("provider:test:legacy-receipt",))
