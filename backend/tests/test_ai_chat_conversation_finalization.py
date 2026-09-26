from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from core.engine_client import EngineUnavailableError
from skeleton.contracts.conversation import (
    ConversationAuthorType,
    ConversationMessage,
    ConversationThread,
    ConversationThreadState,
)


def _now() -> datetime:
    return datetime(2026, 9, 26, 4, 0, tzinfo=timezone.utc)


def _thread_and_user_message():
    thread_id = str(uuid4())
    branch_id = str(uuid4())
    created = _now()
    thread = ConversationThread(
        thread_id=thread_id,
        tenant_id="tenant-a",
        owner_id="owner-a",
        created_at=created,
        updated_at=created,
        version=2,
        message_sequence=1,
        active_branch_id=branch_id,
        state=ConversationThreadState.ACTIVE,
        title="Canonical chat",
        data_class="confidential",
    )
    user_message = ConversationMessage(
        message_id=str(uuid4()),
        thread_id=thread_id,
        branch_id=branch_id,
        sequence=1,
        author_type=ConversationAuthorType.USER,
        created_at=created,
        idempotency_key="client-turn-1",
        content="Explain the invariant.",
        data_class="confidential",
    )
    return thread, user_message


def _request(route, thread_id: str):
    return route.AIChatRequest(
        message="Explain the invariant.",
        thread_id=thread_id,
        idempotency_key="client-turn-1",
        expected_thread_version=1,
    )


@pytest.mark.asyncio
async def test_chat_commits_assistant_only_from_successful_engine_result(
    monkeypatch,
) -> None:
    import routes.ai as route

    thread, user_message = _thread_and_user_message()
    commit_calls = []
    captured_commands = []

    async def append_user_message(*_args, **_kwargs):
        return thread, user_message

    async def active_transcript(*_args, **_kwargs):
        return (user_message,)

    async def commit_assistant_message(thread_id, **kwargs):
        commit_calls.append({"thread_id": thread_id, **kwargs})
        committed = ConversationThread(
            thread_id=thread.thread_id,
            tenant_id=thread.tenant_id,
            owner_id=thread.owner_id,
            created_at=thread.created_at,
            updated_at=thread.updated_at,
            version=3,
            message_sequence=2,
            active_branch_id=thread.active_branch_id,
            state=thread.state,
            title=thread.title,
            data_class=thread.data_class,
        )
        message = ConversationMessage(
            message_id=str(uuid4()),
            thread_id=thread.thread_id,
            branch_id=thread.active_branch_id,
            sequence=2,
            author_type=ConversationAuthorType.ASSISTANT,
            created_at=_now(),
            idempotency_key=kwargs["idempotency_key"],
            content=kwargs["content"],
            parent_message_id=kwargs["causal_user_message_id"],
            causal_user_message_id=kwargs["causal_user_message_id"],
            operation_id=kwargs["operation_id"],
            ai_result_id=kwargs["ai_result_id"],
            context_id=kwargs["context_id"],
            context_digest=kwargs["context_digest"],
            context_source_snapshot=kwargs["context_source_snapshot"],
            context_compiler_version=kwargs["context_compiler_version"],
            data_class="confidential",
        )
        return committed, message

    fake_authority = SimpleNamespace(
        append_user_message=append_user_message,
        active_transcript=active_transcript,
        commit_assistant_message=commit_assistant_message,
    )
    fake_client = SimpleNamespace(
        config=SimpleNamespace(
            service_principal="codedock-backend",
            execution_timeout_s=30.0,
        )
    )

    async def execute(command):
        captured_commands.append(command)
        return SimpleNamespace(
            final_output="Verified terminal answer.",
            execution_id=command.execution_request.execution_id,
            verification="verification:terminal",
            evidence_refs=("evidence:terminal",),
        )

    fake_client.execute = execute

    monkeypatch.setattr(route, "conversation_authority", fake_authority)
    monkeypatch.setattr(route.EngineClient, "from_env", lambda: fake_client)

    response = await route.ai_chat(
        _request(route, thread.thread_id),
        user={"tenant_id": "tenant-a", "email": "owner-a"},
    )

    assert response["success"] is True
    assert response["response"] == "Verified terminal answer."
    assert len(captured_commands) == 1
    assert len(commit_calls) == 1
    call = commit_calls[0]
    execution_id = captured_commands[0].execution_request.execution_id
    assert call["thread_id"] == thread.thread_id
    assert call["causal_user_message_id"] == user_message.message_id
    assert call["operation_id"] == captured_commands[0].operation.operation_id
    assert call["ai_result_id"] == "engine-result:" + execution_id
    assert call["content"] == "Verified terminal answer."
    assert response["assistant_message"]["ai_result_id"] == (
        "engine-result:" + execution_id
    )


@pytest.mark.asyncio
async def test_chat_never_commits_assistant_when_engine_is_unavailable(
    monkeypatch,
) -> None:
    import routes.ai as route

    thread, user_message = _thread_and_user_message()
    commit_calls = []

    async def append_user_message(*_args, **_kwargs):
        return thread, user_message

    async def active_transcript(*_args, **_kwargs):
        return (user_message,)

    async def forbidden_commit(*args, **kwargs):
        commit_calls.append((args, kwargs))
        raise AssertionError("assistant commit must not run after engine failure")

    fake_authority = SimpleNamespace(
        append_user_message=append_user_message,
        active_transcript=active_transcript,
        commit_assistant_message=forbidden_commit,
    )
    fake_client = SimpleNamespace(
        config=SimpleNamespace(
            service_principal="codedock-backend",
            execution_timeout_s=30.0,
        )
    )

    async def execute(_command):
        raise EngineUnavailableError("engine unavailable")

    fake_client.execute = execute

    monkeypatch.setattr(route, "conversation_authority", fake_authority)
    monkeypatch.setattr(route.EngineClient, "from_env", lambda: fake_client)

    response = await route.ai_chat(
        _request(route, thread.thread_id),
        user={"tenant_id": "tenant-a", "email": "owner-a"},
    )

    assert response["success"] is False
    assert response["error_code"] == "engine_unavailable"
    assert commit_calls == []
