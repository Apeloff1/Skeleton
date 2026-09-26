from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from core.engine_client import EngineUnavailableError
from skeleton.contracts.conversation import (
    ConversationAuthorType,
    ConversationMessage,
    ConversationThread,
    ConversationThreadState,
)


def _now() -> datetime:
    return datetime(2026, 9, 26, 5, 0, tzinfo=timezone.utc)


def _conversation():
    thread_id = str(uuid4())
    branch_id = str(uuid4())
    user_message = ConversationMessage(
        message_id=str(uuid4()),
        thread_id=thread_id,
        branch_id=branch_id,
        sequence=1,
        author_type=ConversationAuthorType.USER,
        created_at=_now(),
        idempotency_key="user-turn-1",
        content="Explain this again.",
        data_class="confidential",
    )
    assistant = ConversationMessage(
        message_id=str(uuid4()),
        thread_id=thread_id,
        branch_id=branch_id,
        sequence=2,
        author_type=ConversationAuthorType.ASSISTANT,
        created_at=_now(),
        idempotency_key="assistant-turn-1",
        content="Original answer.",
        parent_message_id=user_message.message_id,
        causal_user_message_id=user_message.message_id,
        operation_id=str(uuid4()),
        ai_result_id="engine-result:original",
        data_class="confidential",
    )
    thread = ConversationThread(
        thread_id=thread_id,
        tenant_id="tenant-a",
        owner_id="owner-a",
        created_at=_now(),
        updated_at=_now(),
        version=3,
        message_sequence=2,
        active_branch_id=branch_id,
        state=ConversationThreadState.ACTIVE,
        title="Regeneration",
        data_class="confidential",
    )
    return thread, user_message, assistant


@pytest.mark.asyncio
async def test_regenerate_route_runs_engine_then_commits_new_branch(
    monkeypatch,
) -> None:
    import core.engine_client as engine_client
    import routes.conversations as route

    thread, user_message, assistant = _conversation()
    engine_commands = []
    regeneration_calls = []

    async def get_thread(*_args, **_kwargs):
        return thread

    async def list_messages(*_args, **_kwargs):
        return (user_message, assistant)

    async def regenerate(thread_id, prior_id, **kwargs):
        regeneration_calls.append(
            {"thread_id": thread_id, "prior_id": prior_id, **kwargs}
        )
        committed_thread = ConversationThread(
            thread_id=thread.thread_id,
            tenant_id=thread.tenant_id,
            owner_id=thread.owner_id,
            created_at=thread.created_at,
            updated_at=thread.updated_at,
            version=4,
            message_sequence=3,
            active_branch_id=str(uuid4()),
            state=thread.state,
            title=thread.title,
            data_class=thread.data_class,
        )
        regenerated = ConversationMessage(
            message_id=str(uuid4()),
            thread_id=thread.thread_id,
            branch_id=committed_thread.active_branch_id,
            sequence=3,
            author_type=ConversationAuthorType.ASSISTANT,
            created_at=_now(),
            idempotency_key=kwargs["idempotency_key"],
            content=kwargs["content"],
            parent_message_id=user_message.message_id,
            supersedes_message_id=assistant.message_id,
            causal_user_message_id=user_message.message_id,
            operation_id=kwargs["operation_id"],
            ai_result_id=kwargs["ai_result_id"],
            context_id=kwargs["context_id"],
            context_digest=kwargs["context_digest"],
            context_source_snapshot=kwargs["context_source_snapshot"],
            context_compiler_version=kwargs["context_compiler_version"],
            data_class=assistant.data_class,
        )
        return committed_thread, regenerated

    authority = SimpleNamespace(
        get_thread=get_thread,
        list_messages=list_messages,
        regenerate_assistant_message=regenerate,
    )
    fake_engine = SimpleNamespace(
        config=SimpleNamespace(
            service_principal="codedock-backend",
            execution_timeout_s=30.0,
        )
    )

    async def execute(command):
        engine_commands.append(command)
        return SimpleNamespace(
            final_output="Regenerated verified answer.",
            execution_id=command.execution_request.execution_id,
            verification="verification:regen",
            evidence_refs=("evidence:regen",),
        )

    fake_engine.execute = execute

    monkeypatch.setattr(route, "conversation_authority", authority)
    monkeypatch.setattr(
        engine_client.EngineClient,
        "from_env",
        lambda: fake_engine,
    )

    response = await route.regenerate_assistant_message(
        thread.thread_id,
        assistant.message_id,
        route.RegenerateMessageRequest(
            idempotency_key="regen-1",
            expected_thread_version=3,
        ),
        user={"tenant_id": "tenant-a", "email": "owner-a"},
    )

    assert len(engine_commands) == 1
    assert len(regeneration_calls) == 1
    command = engine_commands[0]
    commit = regeneration_calls[0]
    assert commit["thread_id"] == thread.thread_id
    assert commit["prior_id"] == assistant.message_id
    assert commit["content"] == "Regenerated verified answer."
    assert commit["expected_thread_version"] == 3
    assert commit["ai_result_id"] == (
        "engine-result:" + command.execution_request.execution_id
    )
    assert commit["operation_id"] == command.operation.operation_id
    assert response["regenerated_from"] == assistant.message_id
    assert response["causal_user_message_id"] == user_message.message_id
    assert response["message"]["supersedes_message_id"] == assistant.message_id
    assert response["message"]["causal_user_message_id"] == user_message.message_id


@pytest.mark.asyncio
async def test_regenerate_route_never_commits_when_engine_unavailable(
    monkeypatch,
) -> None:
    import core.engine_client as engine_client
    import routes.conversations as route

    thread, user_message, assistant = _conversation()
    regeneration_calls = []

    async def get_thread(*_args, **_kwargs):
        return thread

    async def list_messages(*_args, **_kwargs):
        return (user_message, assistant)

    async def forbidden_regenerate(*args, **kwargs):
        regeneration_calls.append((args, kwargs))
        raise AssertionError(
            "conversation regeneration must not commit after engine failure"
        )

    authority = SimpleNamespace(
        get_thread=get_thread,
        list_messages=list_messages,
        regenerate_assistant_message=forbidden_regenerate,
    )
    fake_engine = SimpleNamespace(
        config=SimpleNamespace(
            service_principal="codedock-backend",
            execution_timeout_s=30.0,
        )
    )

    async def execute(_command):
        raise EngineUnavailableError("engine unavailable")

    fake_engine.execute = execute

    monkeypatch.setattr(route, "conversation_authority", authority)
    monkeypatch.setattr(
        engine_client.EngineClient,
        "from_env",
        lambda: fake_engine,
    )

    with pytest.raises(HTTPException) as exc:
        await route.regenerate_assistant_message(
            thread.thread_id,
            assistant.message_id,
            route.RegenerateMessageRequest(
                idempotency_key="regen-2",
                expected_thread_version=3,
            ),
            user={"tenant_id": "tenant-a", "email": "owner-a"},
        )

    assert exc.value.status_code == 503
    assert exc.value.detail == "AI engine is unavailable"
    assert regeneration_calls == []


@pytest.mark.asyncio
async def test_regenerate_route_rejects_user_message_source(
    monkeypatch,
) -> None:
    import routes.conversations as route

    thread, user_message, _assistant = _conversation()

    async def get_thread(*_args, **_kwargs):
        return thread

    async def list_messages(*_args, **_kwargs):
        return (user_message,)

    monkeypatch.setattr(
        route,
        "conversation_authority",
        SimpleNamespace(
            get_thread=get_thread,
            list_messages=list_messages,
        ),
    )

    with pytest.raises(HTTPException) as exc:
        await route.regenerate_assistant_message(
            thread.thread_id,
            user_message.message_id,
            route.RegenerateMessageRequest(
                idempotency_key="regen-user",
                expected_thread_version=3,
            ),
            user={"tenant_id": "tenant-a", "email": "owner-a"},
        )

    assert exc.value.status_code == 409
    assert "only assistant messages" in exc.value.detail
