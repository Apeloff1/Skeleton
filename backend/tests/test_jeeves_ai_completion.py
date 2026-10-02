from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException

from gameforge.jeeves.chat_contract import ChatReq
from routes import jeeves_compose
from skeleton.contracts.conversation import (
    ConversationAuthorType,
    ConversationMessage,
)
from skeleton.persistence.conversation_repository import (
    SQLiteConversationRepository,
)


class AsyncConversationAuthority:
    """Minimal async facade over canonical SQLite conversation authority."""

    def __init__(self, repository: SQLiteConversationRepository) -> None:
        self.repository = repository

    async def create_thread(self, **kwargs):
        return self.repository.create_thread(**kwargs)

    async def get_thread(
        self,
        thread_id: str,
        *,
        tenant_id: str,
        owner_id: str,
    ):
        return self.repository.get_thread(
            thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )

    async def active_transcript(
        self,
        thread_id: str,
        *,
        tenant_id: str,
        owner_id: str,
    ):
        return self.repository.active_transcript(
            thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )

    async def append_user_message(
        self,
        thread_id: str,
        *,
        tenant_id: str,
        owner_id: str,
        content: str,
        idempotency_key: str,
        expected_thread_version: int,
        parent_message_id: str | None = None,
        branch_id: str | None = None,
        supersedes_message_id: str | None = None,
        attachment_refs: tuple[str, ...] = (),
        data_class: str = "confidential",
    ):
        thread = self.repository.get_thread(
            thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        message = ConversationMessage(
            message_id=str(uuid4()),
            thread_id=thread.thread_id,
            branch_id=branch_id or thread.active_branch_id,
            sequence=thread.message_sequence + 1,
            author_type=ConversationAuthorType.USER,
            created_at=datetime.now(timezone.utc),
            idempotency_key=idempotency_key,
            content=content,
            parent_message_id=parent_message_id,
            supersedes_message_id=supersedes_message_id,
            attachment_refs=attachment_refs,
            data_class=thread.data_class,
        )
        return self.repository.append_message(
            message,
            tenant_id=tenant_id,
            owner_id=owner_id,
            expected_thread_version=expected_thread_version,
        )

    async def commit_assistant_message(
        self,
        thread_id: str,
        *,
        tenant_id: str,
        owner_id: str,
        content: str,
        idempotency_key: str,
        expected_thread_version: int,
        causal_user_message_id: str,
        operation_id: str,
        ai_result_id: str,
        context_id: str | None = None,
        context_digest: str | None = None,
        context_source_snapshot: tuple[tuple[str, str], ...] = (),
        context_compiler_version: str | None = None,
        branch_id: str | None = None,
        supersedes_message_id: str | None = None,
        tool_receipt_refs: tuple[str, ...] = (),
        provider_receipt_refs: tuple[str, ...] = (),
        memory_refs: tuple[str, ...] = (),
        citation_refs: tuple[str, ...] = (),
        artifact_refs: tuple[str, ...] = (),
        data_class: str = "confidential",
    ):
        thread = self.repository.get_thread(
            thread_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        message = ConversationMessage(
            message_id=str(uuid4()),
            thread_id=thread.thread_id,
            branch_id=branch_id or thread.active_branch_id,
            sequence=thread.message_sequence + 1,
            author_type=ConversationAuthorType.ASSISTANT,
            created_at=datetime.now(timezone.utc),
            idempotency_key=idempotency_key,
            content=content,
            parent_message_id=causal_user_message_id,
            supersedes_message_id=supersedes_message_id,
            causal_user_message_id=causal_user_message_id,
            operation_id=operation_id,
            ai_result_id=ai_result_id,
            context_id=context_id,
            context_digest=context_digest,
            context_source_snapshot=context_source_snapshot,
            context_compiler_version=context_compiler_version,
            tool_receipt_refs=tool_receipt_refs,
            provider_receipt_refs=provider_receipt_refs,
            memory_refs=memory_refs,
            citation_refs=citation_refs,
            artifact_refs=artifact_refs,
            data_class=thread.data_class,
        )
        return self.repository.append_message(
            message,
            tenant_id=tenant_id,
            owner_id=owner_id,
            expected_thread_version=expected_thread_version,
        )


@pytest.fixture
def canonical_authority(tmp_path, monkeypatch):
    repository = SQLiteConversationRepository(
        tmp_path / "jeeves-ai-completion.sqlite3"
    )
    authority = AsyncConversationAuthority(repository)
    monkeypatch.setattr(
        jeeves_compose,
        "_canonical_authority",
        lambda: authority,
    )
    try:
        yield repository, authority
    finally:
        repository.close()


@pytest.mark.asyncio
async def test_jeeves_preserves_exact_multi_turn_parent_lineage(
    canonical_authority,
) -> None:
    repository, _authority = canonical_authority
    session_id = "lineage-session"

    first = await jeeves_compose._append_canonical_user_turn(
        ChatReq(
            session_id=session_id,
            client_message_id="turn-1",
            message="First question",
        ),
        session_id,
    )
    thread, assistant_one = await jeeves_compose._commit_canonical_assistant_turn(
        authority=first[0],
        thread=first[1],
        user_message=first[2],
        tenant_id=first[3],
        owner_id=first[4],
        session_id=session_id,
        client_message_id="turn-1",
        generated={
            "text": "First answer",
            "model": "local-extractive",
        },
    )

    second = await jeeves_compose._append_canonical_user_turn(
        ChatReq(
            session_id=session_id,
            client_message_id="turn-2",
            message="Second question",
        ),
        session_id,
    )
    _thread, assistant_two = await jeeves_compose._commit_canonical_assistant_turn(
        authority=second[0],
        thread=second[1],
        user_message=second[2],
        tenant_id=second[3],
        owner_id=second[4],
        session_id=session_id,
        client_message_id="turn-2",
        generated={
            "text": "Second answer",
            "model": "local-extractive",
        },
    )

    transcript = repository.active_transcript(
        thread.thread_id,
        tenant_id=first[3],
        owner_id=first[4],
    )
    assert [message.author_type.value for message in transcript] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert transcript[0].parent_message_id is None
    assert assistant_one.parent_message_id == transcript[0].message_id
    assert transcript[2].parent_message_id == assistant_one.message_id
    assert assistant_two.parent_message_id == transcript[2].message_id


@pytest.mark.asyncio
async def test_jeeves_persists_full_engine_context_and_receipt_lineage(
    canonical_authority,
) -> None:
    repository, _authority = canonical_authority
    session_id = "engine-lineage-session"
    turn = await jeeves_compose._append_canonical_user_turn(
        ChatReq(
            session_id=session_id,
            client_message_id="engine-turn-1",
            message="Use the canonical engine.",
        ),
        session_id,
    )
    user_message = turn[2]
    digest = "a" * 64
    source_digest = "b" * 64

    thread, assistant = await jeeves_compose._commit_canonical_assistant_turn(
        authority=turn[0],
        thread=turn[1],
        user_message=user_message,
        tenant_id=turn[3],
        owner_id=turn[4],
        session_id=session_id,
        client_message_id="engine-turn-1",
        generated={
            "text": "Verified engine answer",
            "model": "skeleton-engine",
            "engine_operation_id": "operation-engine-lineage",
            "engine_execution_id": "execution-engine-lineage",
            "engine_context_id": "context-engine-lineage",
            "engine_context_digest": digest,
            "engine_context_source_snapshot": [
                ["segment-engine-lineage", source_digest],
            ],
            "engine_context_compiler_version": "compiler-engine-lineage",
            "engine_provider_receipts": ["provider:local:receipt"],
            "engine_tool_receipts": ["tool:read:receipt"],
            "engine_memory_refs": ["memory:episodic:one"],
            "engine_evidence_refs": ["evidence:one"],
            "engine_artifact_refs": ["artifact:one"],
        },
    )

    assert assistant.operation_id == "operation-engine-lineage"
    assert assistant.ai_result_id == "engine-result:execution-engine-lineage"
    assert assistant.context_id == "context-engine-lineage"
    assert assistant.context_digest == digest
    assert assistant.context_source_snapshot == (
        ("segment-engine-lineage", source_digest),
    )
    assert assistant.context_compiler_version == "compiler-engine-lineage"
    assert assistant.provider_receipt_refs == ("provider:local:receipt",)
    assert assistant.tool_receipt_refs == ("tool:read:receipt",)
    assert assistant.memory_refs == ("memory:episodic:one",)
    assert assistant.citation_refs == ("evidence:one",)
    assert assistant.artifact_refs == ("artifact:one",)

    reopened = repository.get_thread(
        thread.thread_id,
        tenant_id=turn[3],
        owner_id=turn[4],
    )
    assert reopened.message_sequence == 2
    persisted = repository.active_transcript(
        thread.thread_id,
        tenant_id=turn[3],
        owner_id=turn[4],
    )[-1]
    assert persisted == assistant


@pytest.mark.asyncio
async def test_jeeves_engine_failure_stays_retryable_without_fake_success(
    canonical_authority,
    monkeypatch,
) -> None:
    repository, _authority = canonical_authority
    session_id = "retry-session"
    request = ChatReq(
        session_id=session_id,
        client_message_id="retry-turn-1",
        message="Reason about this with the engine.",
    )

    monkeypatch.setattr(
        jeeves_compose,
        "_canon_context",
        lambda _query, top_k=5: [
            {"payload": {"content": "grounding"}},
        ],
    )

    attempts = 0

    async def generate(
        query,
        recalled,
        needs_reasoning,
        conversation_context="",
    ):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise HTTPException(
                status_code=503,
                detail="engine unavailable",
            )
        return {
            "text": "Recovered answer",
            "tier": "paid",
            "model": "skeleton-engine",
            "engine_operation_id": "operation-retry",
            "engine_execution_id": "execution-retry",
            "engine_context_id": "context-retry",
            "engine_context_digest": "c" * 64,
            "engine_context_source_snapshot": [
                ["segment-retry", "d" * 64],
            ],
            "engine_context_compiler_version": "compiler-retry",
            "engine_verification": "verification:retry",
            "engine_evidence_refs": ["evidence:retry"],
            "engine_provider_receipts": ["provider:local:retry"],
            "engine_tool_receipts": [],
            "engine_memory_refs": [],
            "engine_artifact_refs": [],
        }

    monkeypatch.setattr(jeeves_compose, "_generate_text", generate)

    with pytest.raises(HTTPException) as caught:
        await jeeves_compose.chat(request)
    assert caught.value.status_code == 503

    tenant_id, owner_id = jeeves_compose._canonical_session_identity(
        session_id
    )
    thread_id = jeeves_compose._canonical_thread_id(session_id)
    after_failure = repository.active_transcript(
        thread_id,
        tenant_id=tenant_id,
        owner_id=owner_id,
    )
    assert [message.author_type.value for message in after_failure] == [
        "user",
    ]

    recovered = await jeeves_compose.chat(request)
    assert recovered["ok"] is True
    assert recovered["reply"] == "Recovered answer"
    assert recovered["engine_execution_id"] == "execution-retry"

    transcript = repository.active_transcript(
        thread_id,
        tenant_id=tenant_id,
        owner_id=owner_id,
    )
    assert [message.author_type.value for message in transcript] == [
        "user",
        "assistant",
    ]
    assert transcript[1].parent_message_id == transcript[0].message_id
    assert transcript[1].operation_id == "operation-retry"
    assert transcript[1].provider_receipt_refs == (
        "provider:local:retry",
    )
    assert attempts == 2


@pytest.mark.asyncio
async def test_jeeves_rejects_engine_result_with_partial_lineage(
    canonical_authority,
) -> None:
    _repository, _authority = canonical_authority
    session_id = "partial-lineage-session"
    turn = await jeeves_compose._append_canonical_user_turn(
        ChatReq(
            session_id=session_id,
            client_message_id="partial-turn-1",
            message="Do not accept partial lineage.",
        ),
        session_id,
    )

    with pytest.raises(
        ValueError,
        match="missing canonical lineage",
    ):
        await jeeves_compose._commit_canonical_assistant_turn(
            authority=turn[0],
            thread=turn[1],
            user_message=turn[2],
            tenant_id=turn[3],
            owner_id=turn[4],
            session_id=session_id,
            client_message_id="partial-turn-1",
            generated={
                "text": "Unverifiable answer",
                "model": "skeleton-engine",
                "engine_operation_id": "operation-partial",
                "engine_execution_id": "execution-partial",
                # Context identity intentionally omitted.
            },
        )
