from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from skeleton.contracts.conversation import (
    ConversationAuthorType,
    ConversationContractError,
    ConversationMessage,
    ConversationThreadState,
)
from skeleton.persistence.conversation_repository import (
    ConversationAuthorizationError,
    ConversationConflict,
    SQLiteConversationRepository,
)


def _now() -> datetime:
    return datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


def _message(
    *,
    thread_id: str,
    branch_id: str,
    sequence: int,
    author: ConversationAuthorType,
    content: str,
    idempotency_key: str,
    parent_message_id: str | None = None,
    supersedes_message_id: str | None = None,
    causal_user_message_id: str | None = None,
    operation_id: str | None = None,
    ai_result_id: str | None = None,
) -> ConversationMessage:
    return ConversationMessage(
        message_id=str(uuid4()),
        thread_id=thread_id,
        branch_id=branch_id,
        sequence=sequence,
        author_type=author,
        created_at=_now(),
        idempotency_key=idempotency_key,
        content=content,
        parent_message_id=parent_message_id,
        supersedes_message_id=supersedes_message_id,
        causal_user_message_id=causal_user_message_id,
        operation_id=operation_id,
        ai_result_id=ai_result_id,
    )


def test_assistant_message_requires_operation_and_result_binding() -> None:
    with pytest.raises(
        ConversationContractError,
        match="operation_id and ai_result_id",
    ):
        _message(
            thread_id=str(uuid4()),
            branch_id=str(uuid4()),
            sequence=1,
            author=ConversationAuthorType.ASSISTANT,
            content="answer",
            idempotency_key="assistant-1",
            causal_user_message_id=str(uuid4()),
        )


def test_assistant_memory_refs_round_trip_through_sqlite_authority() -> None:
    repo = SQLiteConversationRepository()
    thread = repo.create_thread(
        tenant_id="tenant-a",
        owner_id="owner-a",
        created_at=_now(),
    )
    user = _message(
        thread_id=thread.thread_id,
        branch_id=thread.active_branch_id,
        sequence=1,
        author=ConversationAuthorType.USER,
        content="remember this",
        idempotency_key="user-memory",
    )
    thread, _ = repo.append_message(
        user,
        tenant_id="tenant-a",
        owner_id="owner-a",
        expected_thread_version=thread.version,
    )
    assistant = ConversationMessage(
        message_id=str(uuid4()),
        thread_id=thread.thread_id,
        branch_id=thread.active_branch_id,
        sequence=2,
        author_type=ConversationAuthorType.ASSISTANT,
        created_at=_now(),
        idempotency_key="assistant-memory",
        content="remembered",
        parent_message_id=user.message_id,
        causal_user_message_id=user.message_id,
        operation_id=str(uuid4()),
        ai_result_id="engine-result:memory",
        memory_refs=("memory:abc", "memory:def"),
    )
    thread, stored = repo.append_message(
        assistant,
        tenant_id="tenant-a",
        owner_id="owner-a",
        expected_thread_version=thread.version,
    )

    loaded = repo.list_messages(
        thread.thread_id,
        tenant_id="tenant-a",
        owner_id="owner-a",
    )

    assert stored.memory_refs == ("memory:abc", "memory:def")
    assert loaded[-1].memory_refs == stored.memory_refs


def test_thread_authorization_is_fail_closed() -> None:
    repo = SQLiteConversationRepository()
    thread = repo.create_thread(
        tenant_id="tenant-a",
        owner_id="owner-a",
        created_at=_now(),
    )

    with pytest.raises(ConversationAuthorizationError, match="access denied"):
        repo.get_thread(
            thread.thread_id,
            tenant_id="tenant-a",
            owner_id="owner-b",
        )

    with pytest.raises(ConversationAuthorizationError, match="access denied"):
        repo.get_thread(
            thread.thread_id,
            tenant_id="tenant-b",
            owner_id="owner-a",
        )


def test_append_requires_exact_next_sequence_and_thread_version() -> None:
    repo = SQLiteConversationRepository()
    thread = repo.create_thread(
        tenant_id="tenant-a",
        owner_id="owner-a",
        created_at=_now(),
    )
    message = _message(
        thread_id=thread.thread_id,
        branch_id=thread.active_branch_id,
        sequence=1,
        author=ConversationAuthorType.USER,
        content="hello",
        idempotency_key="user-1",
    )

    updated, stored = repo.append_message(
        message,
        tenant_id="tenant-a",
        owner_id="owner-a",
        expected_thread_version=1,
    )

    assert stored == message
    assert updated.version == 2
    assert updated.message_sequence == 1

    wrong_sequence = _message(
        thread_id=thread.thread_id,
        branch_id=thread.active_branch_id,
        sequence=3,
        author=ConversationAuthorType.USER,
        content="skip",
        idempotency_key="user-2",
        parent_message_id=message.message_id,
    )
    with pytest.raises(ConversationConflict, match="exact-next"):
        repo.append_message(
            wrong_sequence,
            tenant_id="tenant-a",
            owner_id="owner-a",
            expected_thread_version=2,
        )

    next_message = _message(
        thread_id=thread.thread_id,
        branch_id=thread.active_branch_id,
        sequence=2,
        author=ConversationAuthorType.USER,
        content="next",
        idempotency_key="user-3",
        parent_message_id=message.message_id,
    )
    with pytest.raises(ConversationConflict, match="version conflict"):
        repo.append_message(
            next_message,
            tenant_id="tenant-a",
            owner_id="owner-a",
            expected_thread_version=1,
        )


def test_exact_retry_is_idempotent_after_thread_advanced() -> None:
    repo = SQLiteConversationRepository()
    thread = repo.create_thread(
        tenant_id="tenant-a",
        owner_id="owner-a",
        created_at=_now(),
    )
    message = _message(
        thread_id=thread.thread_id,
        branch_id=thread.active_branch_id,
        sequence=1,
        author=ConversationAuthorType.USER,
        content="hello",
        idempotency_key="stable-key",
    )

    first_thread, first = repo.append_message(
        message,
        tenant_id="tenant-a",
        owner_id="owner-a",
        expected_thread_version=1,
    )
    replay_thread, replay = repo.append_message(
        message,
        tenant_id="tenant-a",
        owner_id="owner-a",
        expected_thread_version=1,
    )

    assert replay == first
    assert replay_thread.version == first_thread.version
    assert len(
        repo.list_messages(
            thread.thread_id,
            tenant_id="tenant-a",
            owner_id="owner-a",
        )
    ) == 1


def test_idempotency_key_cannot_be_reused_for_different_content() -> None:
    repo = SQLiteConversationRepository()
    thread = repo.create_thread(
        tenant_id="tenant-a",
        owner_id="owner-a",
        created_at=_now(),
    )
    first = _message(
        thread_id=thread.thread_id,
        branch_id=thread.active_branch_id,
        sequence=1,
        author=ConversationAuthorType.USER,
        content="first",
        idempotency_key="same-key",
    )
    repo.append_message(
        first,
        tenant_id="tenant-a",
        owner_id="owner-a",
        expected_thread_version=1,
    )
    conflicting = _message(
        thread_id=thread.thread_id,
        branch_id=thread.active_branch_id,
        sequence=2,
        author=ConversationAuthorType.USER,
        content="different",
        idempotency_key="same-key",
        parent_message_id=first.message_id,
    )

    with pytest.raises(ConversationConflict, match="idempotency_key"):
        repo.append_message(
            conflicting,
            tenant_id="tenant-a",
            owner_id="owner-a",
            expected_thread_version=2,
        )


def test_regenerate_creates_sibling_branch_without_rewriting_history() -> None:
    repo = SQLiteConversationRepository()
    thread = repo.create_thread(
        tenant_id="tenant-a",
        owner_id="owner-a",
        created_at=_now(),
    )
    branch_a = thread.active_branch_id
    user = _message(
        thread_id=thread.thread_id,
        branch_id=branch_a,
        sequence=1,
        author=ConversationAuthorType.USER,
        content="question",
        idempotency_key="user-1",
    )
    thread, _ = repo.append_message(
        user,
        tenant_id="tenant-a",
        owner_id="owner-a",
        expected_thread_version=1,
    )
    first_answer = _message(
        thread_id=thread.thread_id,
        branch_id=branch_a,
        sequence=2,
        author=ConversationAuthorType.ASSISTANT,
        content="answer one",
        idempotency_key="assistant-1",
        parent_message_id=user.message_id,
        causal_user_message_id=user.message_id,
        operation_id=str(uuid4()),
        ai_result_id="result-1",
    )
    thread, _ = repo.append_message(
        first_answer,
        tenant_id="tenant-a",
        owner_id="owner-a",
        expected_thread_version=thread.version,
    )

    branch_b = str(uuid4())
    regenerated = _message(
        thread_id=thread.thread_id,
        branch_id=branch_b,
        sequence=3,
        author=ConversationAuthorType.ASSISTANT,
        content="answer two",
        idempotency_key="assistant-2",
        parent_message_id=user.message_id,
        supersedes_message_id=first_answer.message_id,
        causal_user_message_id=user.message_id,
        operation_id=str(uuid4()),
        ai_result_id="result-2",
    )
    thread, _ = repo.append_message(
        regenerated,
        tenant_id="tenant-a",
        owner_id="owner-a",
        expected_thread_version=thread.version,
    )

    assert thread.active_branch_id == branch_b
    all_messages = repo.list_messages(
        thread.thread_id,
        tenant_id="tenant-a",
        owner_id="owner-a",
    )
    assert [item.content for item in all_messages] == [
        "question",
        "answer one",
        "answer two",
    ]
    active = repo.active_transcript(
        thread.thread_id,
        tenant_id="tenant-a",
        owner_id="owner-a",
    )
    assert [item.content for item in active] == ["question", "answer two"]


def test_edit_creates_new_user_message_and_preserves_original() -> None:
    repo = SQLiteConversationRepository()
    thread = repo.create_thread(
        tenant_id="tenant-a",
        owner_id="owner-a",
        created_at=_now(),
    )
    original = _message(
        thread_id=thread.thread_id,
        branch_id=thread.active_branch_id,
        sequence=1,
        author=ConversationAuthorType.USER,
        content="original",
        idempotency_key="original",
    )
    thread, _ = repo.append_message(
        original,
        tenant_id="tenant-a",
        owner_id="owner-a",
        expected_thread_version=thread.version,
    )
    edited = _message(
        thread_id=thread.thread_id,
        branch_id=str(uuid4()),
        sequence=2,
        author=ConversationAuthorType.USER,
        content="edited",
        idempotency_key="edit-1",
        supersedes_message_id=original.message_id,
    )
    thread, _ = repo.append_message(
        edited,
        tenant_id="tenant-a",
        owner_id="owner-a",
        expected_thread_version=thread.version,
    )

    messages = repo.list_messages(
        thread.thread_id,
        tenant_id="tenant-a",
        owner_id="owner-a",
    )
    assert [item.content for item in messages] == ["original", "edited"]
    assert messages[1].supersedes_message_id == original.message_id
    assert [item.content for item in repo.active_transcript(
        thread.thread_id,
        tenant_id="tenant-a",
        owner_id="owner-a",
    )] == ["edited"]


def test_archived_thread_rejects_new_messages() -> None:
    repo = SQLiteConversationRepository()
    thread = repo.create_thread(
        tenant_id="tenant-a",
        owner_id="owner-a",
        created_at=_now(),
    )
    archived = repo.set_state(
        thread.thread_id,
        tenant_id="tenant-a",
        owner_id="owner-a",
        expected_version=thread.version,
        state=ConversationThreadState.ARCHIVED,
    )
    message = _message(
        thread_id=thread.thread_id,
        branch_id=thread.active_branch_id,
        sequence=1,
        author=ConversationAuthorType.USER,
        content="late message",
        idempotency_key="late",
    )

    with pytest.raises(ConversationConflict, match="not writable"):
        repo.append_message(
            message,
            tenant_id="tenant-a",
            owner_id="owner-a",
            expected_thread_version=archived.version,
        )


def test_repository_reopens_durable_thread_and_messages(tmp_path) -> None:
    path = tmp_path / "conversations.db"
    first = SQLiteConversationRepository(path)
    thread = first.create_thread(
        tenant_id="tenant-a",
        owner_id="owner-a",
        created_at=_now(),
    )
    message = _message(
        thread_id=thread.thread_id,
        branch_id=thread.active_branch_id,
        sequence=1,
        author=ConversationAuthorType.USER,
        content="durable",
        idempotency_key="durable-1",
    )
    first.append_message(
        message,
        tenant_id="tenant-a",
        owner_id="owner-a",
        expected_thread_version=thread.version,
    )
    first.close()

    reopened = SQLiteConversationRepository(path)
    loaded = reopened.get_thread(
        thread.thread_id,
        tenant_id="tenant-a",
        owner_id="owner-a",
    )
    messages = reopened.list_messages(
        thread.thread_id,
        tenant_id="tenant-a",
        owner_id="owner-a",
    )

    assert loaded.version == 2
    assert loaded.message_sequence == 1
    assert [item.content for item in messages] == ["durable"]
