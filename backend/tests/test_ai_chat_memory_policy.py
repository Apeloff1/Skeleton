from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from skeleton.contracts.conversation import (
    ConversationAuthorType,
    ConversationMessage,
    ConversationThread,
    ConversationThreadState,
)


def _request(route, **memory_policy):
    payload = {
        "message": "Keep this answer for later.",
        "thread_id": "11111111-1111-1111-1111-111111111111",
        "idempotency_key": "memory-policy-turn-1",
        "expected_thread_version": 1,
    }
    if memory_policy:
        payload["memory_policy"] = memory_policy
    return route.AIChatRequest(**payload)


def test_chat_memory_policy_is_default_off() -> None:
    import routes.ai as route

    request = _request(route)
    intent = route._chat_memory_write_intent(
        request=request,
        owner_id="owner-a",
        thread=SimpleNamespace(thread_id=request.thread_id),
        user_message=SimpleNamespace(
            message_id="22222222-2222-2222-2222-222222222222"
        ),
    )

    assert intent is None


def test_chat_memory_policy_is_explicit_and_authenticated_owner_scoped() -> None:
    import routes.ai as route

    request = _request(
        route,
        persist_verified_response=True,
        kind="preference",
        namespace="assistant.preferences",
    )
    intent = route._chat_memory_write_intent(
        request=request,
        owner_id="owner-a",
        thread=SimpleNamespace(thread_id=request.thread_id),
        user_message=SimpleNamespace(
            message_id="22222222-2222-2222-2222-222222222222"
        ),
    )

    assert intent is not None
    assert intent["subject_id"] == "owner-a"
    assert intent["namespace"] == "assistant.preferences"
    assert intent["kind"] == "preference"
    assert intent["content_from"] == "verified_final_output"
    assert intent["idempotency_key"] == (
        "chat-memory:"
        + request.thread_id
        + ":22222222-2222-2222-2222-222222222222:preference"
    )
    assert intent["provenance_refs"] == [
        "conversation:" + request.thread_id,
        (
            "conversation-message:"
            "22222222-2222-2222-2222-222222222222"
        ),
        "user-policy:verified-response-memory",
    ]


def test_chat_memory_policy_rejects_subject_spoofing() -> None:
    import routes.ai as route

    with pytest.raises(ValidationError):
        _request(
            route,
            persist_verified_response=True,
            kind="semantic",
            subject_id="someone-else",
        )


def test_chat_memory_policy_requires_normalized_namespace() -> None:
    import routes.ai as route

    request = _request(
        route,
        persist_verified_response=True,
        namespace=" assistant ",
    )
    with pytest.raises(HTTPException) as exc:
        route._chat_memory_write_intent(
            request=request,
            owner_id="owner-a",
            thread=SimpleNamespace(thread_id=request.thread_id),
            user_message=SimpleNamespace(
                message_id="22222222-2222-2222-2222-222222222222"
            ),
        )

    assert exc.value.status_code == 422


def test_chat_memory_policy_requires_aware_expiry() -> None:
    import routes.ai as route

    request = _request(
        route,
        persist_verified_response=True,
        expires_at=datetime(2027, 1, 1),
    )
    with pytest.raises(HTTPException) as exc:
        route._chat_memory_write_intent(
            request=request,
            owner_id="owner-a",
            thread=SimpleNamespace(thread_id=request.thread_id),
            user_message=SimpleNamespace(
                message_id="22222222-2222-2222-2222-222222222222"
            ),
        )

    assert exc.value.status_code == 422

    aware = _request(
        route,
        persist_verified_response=True,
        expires_at=datetime(2027, 1, 1, tzinfo=timezone.utc),
    )
    intent = route._chat_memory_write_intent(
        request=aware,
        owner_id="owner-a",
        thread=SimpleNamespace(thread_id=aware.thread_id),
        user_message=SimpleNamespace(
            message_id="22222222-2222-2222-2222-222222222222"
        ),
    )
    assert intent is not None
    assert intent["expires_at"].tzinfo is not None


def _canonical_turn():
    now = datetime(2026, 9, 26, 6, 30, tzinfo=timezone.utc)
    thread = ConversationThread(
        thread_id=str(uuid4()),
        tenant_id="tenant-a",
        owner_id="owner-a",
        created_at=now,
        updated_at=now,
        version=2,
        message_sequence=1,
        active_branch_id=str(uuid4()),
        state=ConversationThreadState.ACTIVE,
        title="Memory policy",
        data_class="confidential",
    )
    user_message = ConversationMessage(
        message_id=str(uuid4()),
        thread_id=thread.thread_id,
        branch_id=thread.active_branch_id,
        sequence=1,
        author_type=ConversationAuthorType.USER,
        created_at=now,
        idempotency_key="memory-policy-turn-1",
        content="Keep this answer for later.",
        data_class="confidential",
    )
    return thread, user_message


@pytest.mark.asyncio
async def test_chat_memory_policy_reaches_delegated_engine_command(
    monkeypatch,
) -> None:
    import routes.ai as route

    thread, user_message = _canonical_turn()
    captured = []
    commits = []

    transcript_calls = 0

    async def active_transcript(*_args, **_kwargs):
        nonlocal transcript_calls
        transcript_calls += 1
        return () if transcript_calls == 1 else (user_message,)

    async def append_user_message(*_args, **_kwargs):
        return thread, user_message

    async def commit_assistant_message(thread_id, **kwargs):
        commits.append({"thread_id": thread_id, **kwargs})
        assistant = ConversationMessage(
            message_id=str(uuid4()),
            thread_id=thread.thread_id,
            branch_id=thread.active_branch_id,
            sequence=2,
            author_type=ConversationAuthorType.ASSISTANT,
            created_at=datetime(2026, 9, 26, 6, 31, tzinfo=timezone.utc),
            idempotency_key=kwargs["idempotency_key"],
            content=kwargs["content"],
            parent_message_id=user_message.message_id,
            causal_user_message_id=user_message.message_id,
            operation_id=kwargs["operation_id"],
            ai_result_id=kwargs["ai_result_id"],
            context_id=kwargs["context_id"],
            context_digest=kwargs["context_digest"],
            context_source_snapshot=kwargs["context_source_snapshot"],
            context_compiler_version=kwargs["context_compiler_version"],
            memory_refs=kwargs["memory_refs"],
            data_class="confidential",
        )
        committed_thread = ConversationThread(
            thread_id=thread.thread_id,
            tenant_id=thread.tenant_id,
            owner_id=thread.owner_id,
            created_at=thread.created_at,
            updated_at=assistant.created_at,
            version=3,
            message_sequence=2,
            active_branch_id=thread.active_branch_id,
            state=thread.state,
            title=thread.title,
            data_class=thread.data_class,
        )
        return committed_thread, assistant

    fake_authority = SimpleNamespace(
        active_transcript=active_transcript,
        append_user_message=append_user_message,
        commit_assistant_message=commit_assistant_message,
    )
    fake_engine = SimpleNamespace(
        config=SimpleNamespace(
            service_principal="codedock-backend",
            execution_timeout_s=30.0,
        )
    )

    async def execute(command):
        captured.append(command)
        return SimpleNamespace(
            final_output="Verified memory-worthy answer.",
            execution_id=command.execution_request.execution_id,
            verification="verification:memory",
            evidence_refs=("evidence:memory",),
            tool_receipts=(),
            memory_refs=("memory:canonical-1",),
            artifact_refs=(),
        )

    fake_engine.execute = execute
    monkeypatch.setattr(route, "conversation_authority", fake_authority)
    monkeypatch.setattr(route.EngineClient, "from_env", lambda: fake_engine)

    request = route.AIChatRequest(
        message="Keep this answer for later.",
        thread_id=thread.thread_id,
        idempotency_key="memory-policy-turn-1",
        expected_thread_version=1,
        memory_policy={
            "persist_verified_response": True,
            "kind": "semantic",
            "namespace": "assistant",
        },
    )
    response = await route.ai_chat(
        request,
        user={"tenant_id": "tenant-a", "email": "owner-a"},
    )

    assert response["success"] is True
    assert len(captured) == 1
    command = captured[0]
    intent = command.execution_request.context_policy["memory_write_intent"]
    assert intent["subject_id"] == "owner-a"
    assert intent["namespace"] == "assistant"
    assert intent["kind"] == "semantic"
    assert intent["content_from"] == "verified_final_output"
    assert "engine:memory" in command.delegated_authority.scopes
    assert response["engine_memory_refs"] == ["memory:canonical-1"]
    assert commits[0]["memory_refs"] == ("memory:canonical-1",)


@pytest.mark.asyncio
async def test_chat_memory_policy_fails_closed_without_canonical_engine(
    monkeypatch,
) -> None:
    import routes.ai as route

    thread, user_message = _canonical_turn()
    transcript_calls = 0
    calls = {"legacy": 0, "commit": 0}

    async def active_transcript(*_args, **_kwargs):
        nonlocal transcript_calls
        transcript_calls += 1
        return () if transcript_calls == 1 else (user_message,)

    async def append_user_message(*_args, **_kwargs):
        return thread, user_message

    async def forbidden_commit(*_args, **_kwargs):
        calls["commit"] += 1
        raise AssertionError("memory opt-in must not commit without engine")

    async def forbidden_legacy(*_args, **_kwargs):
        calls["legacy"] += 1
        raise AssertionError(
            "memory opt-in must not fall back to legacy provider execution"
        )

    monkeypatch.setattr(
        route,
        "conversation_authority",
        SimpleNamespace(
            active_transcript=active_transcript,
            append_user_message=append_user_message,
            commit_assistant_message=forbidden_commit,
        ),
    )
    monkeypatch.setattr(route.EngineClient, "from_env", lambda: None)
    monkeypatch.setattr(route, "call_llm", forbidden_legacy)

    response = await route.ai_chat(
        route.AIChatRequest(
            message="Keep this answer for later.",
            thread_id=thread.thread_id,
            idempotency_key="memory-policy-turn-1",
            expected_thread_version=1,
            memory_policy={
                "persist_verified_response": True,
                "kind": "semantic",
            },
        ),
        user={"tenant_id": "tenant-a", "email": "owner-a"},
    )

    assert response["success"] is False
    assert response["error_code"] == "memory_persistence_unavailable"
    assert calls == {"legacy": 0, "commit": 0}
