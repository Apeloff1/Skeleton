from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from core.conversations import (
    MongoConversationAuthority,
    _message_doc,
)
from skeleton.contracts.conversation import (
    ConversationAuthorType,
    ConversationMessage,
    ConversationThread,
    ConversationThreadState,
)
from skeleton.persistence.conversation_repository import ConversationConflict


def _now():
    return datetime(2026, 9, 23, 19, 0, tzinfo=timezone.utc)


def _thread() -> ConversationThread:
    return ConversationThread(
        thread_id=str(uuid4()),
        tenant_id="tenant-a",
        owner_id="owner-a",
        created_at=_now(),
        updated_at=_now(),
        version=3,
        message_sequence=2,
        active_branch_id=str(uuid4()),
        state=ConversationThreadState.ACTIVE,
        title="Thread",
    )


def _user(thread: ConversationThread) -> ConversationMessage:
    return ConversationMessage(
        message_id=str(uuid4()),
        thread_id=thread.thread_id,
        branch_id=thread.active_branch_id,
        sequence=1,
        author_type=ConversationAuthorType.USER,
        created_at=_now(),
        idempotency_key="user-1",
        content="question",
    )


def _assistant(
    thread: ConversationThread,
    user: ConversationMessage,
) -> ConversationMessage:
    return ConversationMessage(
        message_id=str(uuid4()),
        thread_id=thread.thread_id,
        branch_id=thread.active_branch_id,
        sequence=2,
        author_type=ConversationAuthorType.ASSISTANT,
        created_at=_now(),
        idempotency_key="assistant-1",
        content="answer",
        parent_message_id=user.message_id,
        causal_user_message_id=user.message_id,
        operation_id=str(uuid4()),
        ai_result_id="result-1",
        data_class="confidential",
    )


@pytest.mark.asyncio
async def test_regeneration_preserves_causal_user_and_creates_fresh_branch() -> None:
    thread = _thread()
    user = _user(thread)
    prior = _assistant(thread, user)
    captured = {}

    authority = object.__new__(MongoConversationAuthority)
    authority.messages = SimpleNamespace(
        find_one=lambda *args, **kwargs: None
    )

    async def find_one(*args, **kwargs):
        captured["query"] = args[0]
        return _message_doc(prior)

    authority.messages.find_one = find_one

    async def get_thread(thread_id, **kwargs):
        assert thread_id == thread.thread_id
        return thread

    async def commit_assistant_message(thread_id, **kwargs):
        captured["commit"] = {"thread_id": thread_id, **kwargs}
        regenerated = ConversationMessage(
            message_id=str(uuid4()),
            thread_id=thread_id,
            branch_id=kwargs["branch_id"],
            sequence=3,
            author_type=ConversationAuthorType.ASSISTANT,
            created_at=_now(),
            idempotency_key=kwargs["idempotency_key"],
            content=kwargs["content"],
            parent_message_id=kwargs["causal_user_message_id"],
            supersedes_message_id=kwargs["supersedes_message_id"],
            causal_user_message_id=kwargs["causal_user_message_id"],
            operation_id=kwargs["operation_id"],
            ai_result_id=kwargs["ai_result_id"],
            data_class=kwargs["data_class"],
        )
        return thread, regenerated

    authority.get_thread = get_thread
    authority.commit_assistant_message = commit_assistant_message

    _, regenerated = await MongoConversationAuthority.regenerate_assistant_message(
        authority,
        thread.thread_id,
        prior.message_id,
        tenant_id="tenant-a",
        owner_id="owner-a",
        content="better answer",
        idempotency_key="regen-1",
        expected_thread_version=3,
        operation_id=str(uuid4()),
        ai_result_id="result-2",
    )

    assert captured["query"]["_id"] == prior.message_id
    assert captured["query"]["sequence"] == {"$lte": thread.message_sequence}
    assert captured["commit"]["causal_user_message_id"] == user.message_id
    assert captured["commit"]["supersedes_message_id"] == prior.message_id
    assert captured["commit"]["branch_id"] != prior.branch_id
    assert regenerated.supersedes_message_id == prior.message_id
    assert regenerated.causal_user_message_id == user.message_id
    assert regenerated.operation_id == captured["commit"]["operation_id"]
    assert regenerated.ai_result_id == "result-2"


@pytest.mark.asyncio
async def test_regeneration_rejects_non_assistant_source() -> None:
    thread = _thread()
    prior = _user(thread)
    authority = object.__new__(MongoConversationAuthority)

    async def find_one(*args, **kwargs):
        return _message_doc(prior)

    authority.messages = SimpleNamespace(find_one=find_one)

    async def get_thread(*args, **kwargs):
        return thread

    authority.get_thread = get_thread

    with pytest.raises(ConversationConflict, match="only assistant"):
        await MongoConversationAuthority.regenerate_assistant_message(
            authority,
            thread.thread_id,
            prior.message_id,
            tenant_id="tenant-a",
            owner_id="owner-a",
            content="forged answer",
            idempotency_key="regen-1",
            expected_thread_version=3,
            operation_id=str(uuid4()),
            ai_result_id="result-2",
        )
