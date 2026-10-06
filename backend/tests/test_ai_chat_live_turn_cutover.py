from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.engine_client import EngineClientConfig
from skeleton.contracts.conversation import (
    ConversationAuthorType,
    ConversationMessage,
    ConversationThread,
    ConversationThreadState,
)


NOW = datetime(2026, 10, 6, 4, 0, tzinfo=timezone.utc)


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


def test_live_chat_writes_durable_turn_and_reconnectable_events(
    route,
    client,
    monkeypatch,
):
    thread_id = str(uuid4())
    branch_id = str(uuid4())
    user_id = str(uuid4())
    operation_id = str(
        uuid5(
            NAMESPACE_URL,
            "skeleton-ai-chat:" + thread_id + ":" + user_id,
        )
    )
    execution_id = str(
        uuid5(
            NAMESPACE_URL,
            "skeleton-ai-chat-execution:" + operation_id,
        )
    )

    after_user = ConversationThread(
        thread_id=thread_id,
        tenant_id="default",
        owner_id="anonymous",
        created_at=NOW,
        updated_at=NOW,
        version=2,
        message_sequence=1,
        active_branch_id=branch_id,
        state=ConversationThreadState.ACTIVE,
        title="Durable chat",
    )
    user_message = ConversationMessage(
        message_id=user_id,
        thread_id=thread_id,
        branch_id=branch_id,
        sequence=1,
        author_type=ConversationAuthorType.USER,
        created_at=NOW,
        idempotency_key="durable-1",
        content="explain durable chat",
    )
    after_assistant = ConversationThread(
        thread_id=thread_id,
        tenant_id="default",
        owner_id="anonymous",
        created_at=NOW,
        updated_at=NOW,
        version=3,
        message_sequence=2,
        active_branch_id=branch_id,
        state=ConversationThreadState.ACTIVE,
        title="Durable chat",
    )
    assistant_message = ConversationMessage(
        message_id=str(uuid4()),
        thread_id=thread_id,
        branch_id=branch_id,
        sequence=2,
        author_type=ConversationAuthorType.ASSISTANT,
        created_at=NOW,
        idempotency_key="durable-1:assistant",
        content="durable answer",
        parent_message_id=user_id,
        causal_user_message_id=user_id,
        operation_id=operation_id,
        ai_result_id="engine-result:" + execution_id,
        provider_receipt_refs=("provider:local:receipt-1",),
    )
    committed = {"value": False}

    async def active_transcript(*_args, **_kwargs):
        if committed["value"]:
            return (user_message, assistant_message)
        return (user_message,)

    async def append_user_message(*_args, **_kwargs):
        return after_user, user_message

    async def commit_assistant_message(*_args, **_kwargs):
        committed["value"] = True
        return after_assistant, assistant_message

    async def get_thread(*_args, **_kwargs):
        return after_assistant if committed["value"] else after_user

    monkeypatch.setattr(
        route,
        "conversation_authority",
        SimpleNamespace(
            active_transcript=active_transcript,
            append_user_message=append_user_message,
            commit_assistant_message=commit_assistant_message,
            get_thread=get_thread,
        ),
    )

    class FakeEngine:
        config = EngineClientConfig(
            base_url="http://skeleton:8001",
            service_principal="codedock-backend",
            execution_timeout_s=5,
        )

        async def execute(self, command):
            assert command.operation.operation_id == operation_id
            assert command.execution_request.execution_id == execution_id
            return SimpleNamespace(
                final_output="durable answer",
                execution_id=execution_id,
                verification="verification:ok",
                evidence_refs=("evidence:1",),
                provider_receipts=("provider:local:receipt-1",),
                tool_receipts=(),
                memory_refs=(),
                artifact_refs=(),
            )

    fake_engine = FakeEngine()
    monkeypatch.setattr(
        route.EngineClient,
        "from_env",
        classmethod(lambda cls, **_kwargs: fake_engine),
    )

    response = client.post(
        "/ai/chat",
        json={
            "message": "explain durable chat",
            "thread_id": thread_id,
            "idempotency_key": "durable-1",
            "expected_thread_version": 1,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["operation_id"] == operation_id
    assert body["turn_state"] == "complete"

    events_response = client.get(
        f"/ai/chat/turns/{thread_id}/events",
        params={"idempotency_key": "durable-1"},
    )
    assert events_response.status_code == 200
    events_body = events_response.json()
    assert events_body["operation_id"] == operation_id
    assert events_body["turn_state"] == "complete"
    assert events_body["terminal"] is True
    assert [event["to_state"] for event in events_body["events"]] == [
        "admitted",
        "user_message_committed",
        "context_compiling",
        "routing",
        "model_running",
        "verifying",
        "finalizing",
        "assistant_message_committed",
        "complete",
    ]
    assert events_body["cursor"]["last_seen_sequence"] == 9
    assert len(events_body["cursor"]["last_event_digest"]) == 64
    assert len(events_body["page_digest"]) == 64

    rendered = repr(events_body["events"])
    assert "durable answer" not in rendered
    assert "explain durable chat" not in rendered
    assert "evidence:1" not in rendered


def test_event_resume_requires_digest_for_nonzero_cursor(
    route,
    client,
    monkeypatch,
):
    thread_id = str(uuid4())
    branch_id = str(uuid4())
    user_id = str(uuid4())
    user_message = ConversationMessage(
        message_id=user_id,
        thread_id=thread_id,
        branch_id=branch_id,
        sequence=1,
        author_type=ConversationAuthorType.USER,
        created_at=NOW,
        idempotency_key="resume-1",
        content="hello",
    )
    thread = ConversationThread(
        thread_id=thread_id,
        tenant_id="default",
        owner_id="anonymous",
        created_at=NOW,
        updated_at=NOW,
        version=2,
        message_sequence=1,
        active_branch_id=branch_id,
        state=ConversationThreadState.ACTIVE,
        title="resume",
    )

    async def get_thread(*_args, **_kwargs):
        return thread

    async def active_transcript(*_args, **_kwargs):
        return (user_message,)

    monkeypatch.setattr(
        route,
        "conversation_authority",
        SimpleNamespace(
            get_thread=get_thread,
            active_transcript=active_transcript,
        ),
    )

    operation_id, _ = route._chat_turn_ids(thread_id, user_id)
    awaitable = route.chat_turn_lifecycle.begin(
        thread=thread,
        user_message=user_message,
        operation_id=operation_id,
        request_digest="a" * 64,
        tenant_id="default",
        owner_id="anonymous",
    )

    import asyncio

    asyncio.run(awaitable)

    response = client.get(
        f"/ai/chat/turns/{thread_id}/events",
        params={
            "idempotency_key": "resume-1",
            "after_sequence": 1,
        },
    )
    assert response.status_code == 422
