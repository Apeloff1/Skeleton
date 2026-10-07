from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from skeleton.contracts.conversation import (
    ConversationAuthorType,
    ConversationMessage,
)
from skeleton.persistence.conversation_repository import SQLiteConversationRepository


NOW = datetime(2026, 9, 24, 2, 45, tzinfo=timezone.utc)


def test_sqlite_persists_context_binding_on_assistant_message(tmp_path):
    path = tmp_path / "conversation.db"
    repo = SQLiteConversationRepository(path)
    thread = repo.create_thread(
        tenant_id="tenant-a",
        owner_id="owner-a",
        created_at=NOW,
    )
    user = ConversationMessage(
        message_id=str(uuid4()),
        thread_id=thread.thread_id,
        branch_id=thread.active_branch_id,
        sequence=1,
        author_type=ConversationAuthorType.USER,
        created_at=NOW,
        idempotency_key="user-1",
        content="question",
    )
    thread, _ = repo.append_message(
        user,
        tenant_id="tenant-a",
        owner_id="owner-a",
        expected_thread_version=1,
    )

    source_id = str(uuid4())
    context_id = str(uuid4())
    context_digest = "a" * 64
    snapshot = ((source_id, "b" * 64),)
    assistant = ConversationMessage(
        message_id=str(uuid4()),
        thread_id=thread.thread_id,
        branch_id=thread.active_branch_id,
        sequence=2,
        author_type=ConversationAuthorType.ASSISTANT,
        created_at=NOW,
        idempotency_key="assistant-1",
        content="answer",
        parent_message_id=user.message_id,
        causal_user_message_id=user.message_id,
        operation_id=str(uuid4()),
        ai_result_id="provider-result:test:1",
        context_id=context_id,
        context_digest=context_digest,
        context_source_snapshot=snapshot,
        context_compiler_version="context-compiler-v1",
    )
    repo.append_message(
        assistant,
        tenant_id="tenant-a",
        owner_id="owner-a",
        expected_thread_version=thread.version,
    )
    repo.close()

    reopened = SQLiteConversationRepository(path)
    transcript = reopened.active_transcript(
        thread.thread_id,
        tenant_id="tenant-a",
        owner_id="owner-a",
    )
    restored = transcript[-1]
    assert restored.context_id == context_id
    assert restored.context_digest == context_digest
    assert restored.context_source_snapshot == snapshot
    assert restored.context_compiler_version == "context-compiler-v1"
    reopened.close()


def test_legacy_assistant_without_context_binding_remains_valid():
    message = ConversationMessage(
        message_id=str(uuid4()),
        thread_id=str(uuid4()),
        branch_id=str(uuid4()),
        sequence=2,
        author_type=ConversationAuthorType.ASSISTANT,
        created_at=NOW,
        idempotency_key="legacy",
        content="legacy answer",
        causal_user_message_id=str(uuid4()),
        operation_id=str(uuid4()),
        ai_result_id="legacy-result",
    )
    assert message.context_id is None
    assert message.context_source_snapshot == ()
