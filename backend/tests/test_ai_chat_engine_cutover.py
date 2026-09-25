from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.engine_client import EngineClientConfig, EngineUnavailableError
from skeleton.contracts.conversation import (
    ConversationAuthorType,
    ConversationMessage,
    ConversationThread,
    ConversationThreadState,
)


def _now():
    return datetime(2026, 9, 25, 7, 0, tzinfo=timezone.utc)


def _thread(*, version: int = 1, sequence: int = 0) -> ConversationThread:
    return ConversationThread(
        thread_id=str(uuid4()),
        tenant_id="default",
        owner_id="anonymous",
        created_at=_now(),
        updated_at=_now(),
        version=version,
        message_sequence=sequence,
        active_branch_id=str(uuid4()),
        state=ConversationThreadState.ACTIVE,
        title="Engine cutover",
    )


@pytest.fixture
def route(monkeypatch):
    import routes.ai as ai
    import routes.gameforge_auth as auth

    monkeypatch.setattr(auth, "_enforced", lambda: False)
    return ai


@pytest.fixture
def client(route):
    app = FastAPI()
    app.include_router(route.router)
    with TestClient(app) as test_client:
        yield test_client


def test_configured_chat_routes_through_engine_and_commits_engine_lineage(
    route,
    client,
    monkeypatch,
):
    initial = _thread()
    prior_user = ConversationMessage(
        message_id=str(uuid4()),
        thread_id=initial.thread_id,
        branch_id=initial.active_branch_id,
        sequence=1,
        author_type=ConversationAuthorType.USER,
        created_at=_now(),
        idempotency_key="prior-user",
        content="prior question",
    )
    prior_assistant = ConversationMessage(
        message_id=str(uuid4()),
        thread_id=initial.thread_id,
        branch_id=initial.active_branch_id,
        sequence=2,
        author_type=ConversationAuthorType.ASSISTANT,
        created_at=_now(),
        idempotency_key="prior-assistant",
        content="prior answer",
        parent_message_id=prior_user.message_id,
        causal_user_message_id=prior_user.message_id,
        operation_id=str(uuid4()),
        ai_result_id="provider-result:legacy:prior",
    )
    user_message = ConversationMessage(
        message_id=str(uuid4()),
        thread_id=initial.thread_id,
        branch_id=initial.active_branch_id,
        sequence=3,
        author_type=ConversationAuthorType.USER,
        created_at=_now(),
        idempotency_key="engine-client-1",
        content="new question",
        parent_message_id=prior_assistant.message_id,
    )
    after_user = ConversationThread(
        thread_id=initial.thread_id,
        tenant_id=initial.tenant_id,
        owner_id=initial.owner_id,
        created_at=initial.created_at,
        updated_at=_now(),
        version=2,
        message_sequence=3,
        active_branch_id=initial.active_branch_id,
        state=initial.state,
        title=initial.title,
        data_class=initial.data_class,
    )
    operation_id = str(
        uuid5(
            NAMESPACE_URL,
            "skeleton-ai-chat:" + initial.thread_id + ":" + user_message.message_id,
        )
    )
    execution_id = str(
        uuid5(
            NAMESPACE_URL,
            "skeleton-ai-chat-execution:" + operation_id,
        )
    )
    assistant = ConversationMessage(
        message_id=str(uuid4()),
        thread_id=initial.thread_id,
        branch_id=initial.active_branch_id,
        sequence=4,
        author_type=ConversationAuthorType.ASSISTANT,
        created_at=_now(),
        idempotency_key="engine-client-1:assistant",
        content="engine answer",
        parent_message_id=user_message.message_id,
        causal_user_message_id=user_message.message_id,
        operation_id=operation_id,
        ai_result_id="engine-result:" + execution_id,
    )
    committed = ConversationThread(
        thread_id=initial.thread_id,
        tenant_id=initial.tenant_id,
        owner_id=initial.owner_id,
        created_at=initial.created_at,
        updated_at=_now(),
        version=3,
        message_sequence=4,
        active_branch_id=initial.active_branch_id,
        state=initial.state,
        title=initial.title,
        data_class=initial.data_class,
    )
    captured = {}

    async def append_user_message(*args, **kwargs):
        return after_user, user_message

    async def active_transcript(*args, **kwargs):
        return prior_user, prior_assistant, user_message

    async def commit_assistant_message(thread_id, **kwargs):
        captured["commit"] = {"thread_id": thread_id, **kwargs}
        return committed, assistant

    async def legacy_provider_must_not_run(*args, **kwargs):
        raise AssertionError(
            "configured engine path must not execute backend provider facade"
        )

    class FakeEngineClient:
        config = EngineClientConfig(
            base_url="http://skeleton:8001",
            service_principal="codedock-backend",
            execution_timeout_s=5,
        )

        async def execute(self, command):
            captured["command"] = command
            return SimpleNamespace(
                operation_id=command.operation.operation_id,
                execution_id=command.execution_request.execution_id,
                final_output="engine answer",
                verification="verification:engine-test",
                evidence_refs=("evidence:engine-test",),
            )

    fake_client = FakeEngineClient()
    monkeypatch.setattr(
        route.EngineClient,
        "from_env",
        classmethod(lambda cls, **kwargs: fake_client),
    )
    monkeypatch.setattr(
        route,
        "conversation_authority",
        SimpleNamespace(
            append_user_message=append_user_message,
            active_transcript=active_transcript,
            commit_assistant_message=commit_assistant_message,
        ),
    )
    monkeypatch.setattr(route, "call_llm", legacy_provider_must_not_run)

    response = client.post(
        "/ai/chat",
        json={
            "message": "new question",
            "thread_id": initial.thread_id,
            "idempotency_key": "engine-client-1",
            "expected_thread_version": 1,
            "context": "ephemeral code evidence",
        },
    )

    assert response.status_code == 200
    body = response.json()
    command = captured["command"]
    assert command.operation.operation_id == operation_id
    assert command.execution_request.execution_id == execution_id
    assert command.operation.actor_id == "anonymous"
    assert command.operation.tenant_id == "default"
    assert command.operation.capability == "assistant.chat"
    assert command.execution_request.context_policy["verification_profile"] == "assistant_proposal"
    assert command.delegated_authority.service_principal == "codedock-backend"
    assert command.compiled_context.context_id == body["context"]["context_id"]
    assert command.compiled_context.context_digest == body["context"]["context_digest"]
    assert command.compiled_context.history == (
        ("user", "prior question"),
        ("assistant", "prior answer"),
    )
    assert "conversation:" + initial.thread_id in command.context_seed_refs
    assert any(
        ref.startswith("ephemeral-context-sha256:")
        for ref in command.context_seed_refs
    )
    assert captured["commit"]["ai_result_id"] == "engine-result:" + execution_id
    assert captured["commit"]["operation_id"] == operation_id
    assert body["success"] is True
    assert body["response"] == "engine answer"
    assert body["provider"] == "skeleton-engine"
    assert body["model"] == "engine-routed"
    assert body["provider_request_id"] is None
    assert body["engine_execution_id"] == execution_id
    assert body["engine_verification"] == "verification:engine-test"
    assert body["engine_evidence_refs"] == ["evidence:engine-test"]


def test_configured_engine_outage_never_falls_back_to_backend_provider(
    route,
    client,
    monkeypatch,
):
    initial = _thread()
    user_message = ConversationMessage(
        message_id=str(uuid4()),
        thread_id=initial.thread_id,
        branch_id=initial.active_branch_id,
        sequence=1,
        author_type=ConversationAuthorType.USER,
        created_at=_now(),
        idempotency_key="engine-outage",
        content="question",
    )
    after_user = ConversationThread(
        thread_id=initial.thread_id,
        tenant_id=initial.tenant_id,
        owner_id=initial.owner_id,
        created_at=initial.created_at,
        updated_at=_now(),
        version=2,
        message_sequence=1,
        active_branch_id=initial.active_branch_id,
        state=initial.state,
        title=initial.title,
        data_class=initial.data_class,
    )
    committed = {"assistant": 0, "legacy": 0}

    async def append_user_message(*args, **kwargs):
        return after_user, user_message

    async def active_transcript(*args, **kwargs):
        return (user_message,)

    async def commit_assistant_message(*args, **kwargs):
        committed["assistant"] += 1
        raise AssertionError("failed engine execution must not commit assistant")

    async def legacy_provider(*args, **kwargs):
        committed["legacy"] += 1
        raise AssertionError("engine outage must not invoke local provider")

    class OfflineEngineClient:
        config = EngineClientConfig(
            base_url="http://skeleton:8001",
            execution_timeout_s=5,
        )

        async def execute(self, command):
            raise EngineUnavailableError("offline")

    offline = OfflineEngineClient()
    monkeypatch.setattr(
        route.EngineClient,
        "from_env",
        classmethod(lambda cls, **kwargs: offline),
    )
    monkeypatch.setattr(
        route,
        "conversation_authority",
        SimpleNamespace(
            append_user_message=append_user_message,
            active_transcript=active_transcript,
            commit_assistant_message=commit_assistant_message,
        ),
    )
    monkeypatch.setattr(route, "call_llm", legacy_provider)

    response = client.post(
        "/ai/chat",
        json={
            "message": "question",
            "thread_id": initial.thread_id,
            "idempotency_key": "engine-outage",
            "expected_thread_version": 1,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["error_code"] == "engine_unavailable"
    assert body["provider"] == "skeleton-engine"
    assert committed["assistant"] == 0
    assert committed["legacy"] == 0
    assert body["user_message"]["message_id"] == user_message.message_id
    assert body["thread"]["version"] == 2
