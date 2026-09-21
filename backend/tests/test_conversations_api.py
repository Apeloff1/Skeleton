from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from skeleton.contracts.conversation import (
    ConversationAuthorType,
    ConversationMessage,
    ConversationThread,
    ConversationThreadState,
)
from skeleton.persistence.conversation_repository import (
    ConversationConflict,
    ConversationNotFound,
)


def _thread(*, version: int = 1, sequence: int = 0) -> ConversationThread:
    now = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
    return ConversationThread(
        thread_id=str(uuid4()),
        tenant_id="default",
        owner_id="anonymous",
        created_at=now,
        updated_at=now,
        version=version,
        message_sequence=sequence,
        active_branch_id=str(uuid4()),
        state=ConversationThreadState.ACTIVE,
        title="Thread",
    )


def _message(thread: ConversationThread, *, sequence: int = 1) -> ConversationMessage:
    return ConversationMessage(
        message_id=str(uuid4()),
        thread_id=thread.thread_id,
        branch_id=thread.active_branch_id,
        sequence=sequence,
        author_type=ConversationAuthorType.USER,
        created_at=datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc),
        idempotency_key=f"user-{sequence}",
        content=f"message-{sequence}",
    )


@pytest.fixture
def route(monkeypatch):
    import routes.gameforge_auth as auth
    import routes.conversations as conversations

    monkeypatch.setattr(auth, "_enforced", lambda: False)
    return conversations


@pytest.fixture
def app_client(route):
    app = FastAPI()
    app.include_router(route.router)
    with TestClient(app) as client:
        yield client


def test_create_conversation_uses_authenticated_projection_identity(
    route,
    app_client,
    monkeypatch,
):
    created = _thread()
    captured = {}

    async def create_thread(**kwargs):
        captured.update(kwargs)
        return created

    monkeypatch.setattr(
        route,
        "conversation_authority",
        SimpleNamespace(create_thread=create_thread),
    )

    response = app_client.post(
        "/api/v1/conversations",
        json={"title": "Architecture", "data_class": "confidential"},
    )

    assert response.status_code == 200
    assert response.json()["thread"]["thread_id"] == created.thread_id
    assert captured["tenant_id"] == "default"
    assert captured["owner_id"] == "anonymous"
    assert captured["title"] == "Architecture"


def test_cross_owner_or_unknown_thread_is_exposed_only_as_not_found(
    route,
    app_client,
    monkeypatch,
):
    async def get_thread(*args, **kwargs):
        raise ConversationNotFound("hidden-thread")

    monkeypatch.setattr(
        route,
        "conversation_authority",
        SimpleNamespace(get_thread=get_thread),
    )

    response = app_client.get("/api/v1/conversations/hidden-thread")

    assert response.status_code == 404
    assert response.json()["detail"] == "Conversation not found"
    assert "owner" not in response.text.lower()


def test_append_user_message_passes_version_and_idempotency(
    route,
    app_client,
    monkeypatch,
):
    original = _thread()
    message = _message(original)
    updated = ConversationThread(
        **{
            **original.__dict__,
        }
    ) if False else _thread(version=2, sequence=1)
    # Keep identity stable while advancing version/sequence.
    updated = ConversationThread(
        thread_id=original.thread_id,
        tenant_id=original.tenant_id,
        owner_id=original.owner_id,
        created_at=original.created_at,
        updated_at=original.updated_at,
        version=2,
        message_sequence=1,
        active_branch_id=original.active_branch_id,
        state=original.state,
        title=original.title,
        data_class=original.data_class,
    )
    captured = {}

    async def append_user_message(thread_id, **kwargs):
        captured["thread_id"] = thread_id
        captured.update(kwargs)
        return updated, message

    monkeypatch.setattr(
        route,
        "conversation_authority",
        SimpleNamespace(append_user_message=append_user_message),
    )

    response = app_client.post(
        f"/api/v1/conversations/{original.thread_id}/messages",
        json={
            "content": "hello",
            "idempotency_key": "client-message-1",
            "expected_thread_version": 1,
        },
    )

    assert response.status_code == 200
    assert captured["thread_id"] == original.thread_id
    assert captured["idempotency_key"] == "client-message-1"
    assert captured["expected_thread_version"] == 1
    assert response.json()["thread"]["version"] == 2


def test_append_conflict_maps_to_http_409(route, app_client, monkeypatch):
    async def append_user_message(*args, **kwargs):
        raise ConversationConflict("thread version conflict")

    monkeypatch.setattr(
        route,
        "conversation_authority",
        SimpleNamespace(append_user_message=append_user_message),
    )

    response = app_client.post(
        f"/api/v1/conversations/{uuid4()}/messages",
        json={
            "content": "hello",
            "idempotency_key": "client-message-1",
            "expected_thread_version": 3,
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "thread version conflict"


def test_active_projection_uses_server_transcript(route, app_client, monkeypatch):
    thread = _thread(version=3, sequence=2)
    first = _message(thread, sequence=1)
    second = ConversationMessage(
        message_id=str(uuid4()),
        thread_id=thread.thread_id,
        branch_id=thread.active_branch_id,
        sequence=2,
        author_type=ConversationAuthorType.ASSISTANT,
        created_at=datetime(2026, 9, 21, 12, 1, tzinfo=timezone.utc),
        idempotency_key="assistant-1",
        content="answer",
        parent_message_id=first.message_id,
        causal_user_message_id=first.message_id,
        operation_id=str(uuid4()),
        ai_result_id="result-1",
    )
    captured = {"active": 0, "list": 0}

    async def active_transcript(*args, **kwargs):
        captured["active"] += 1
        return first, second

    async def list_messages(*args, **kwargs):
        captured["list"] += 1
        return ()

    monkeypatch.setattr(
        route,
        "conversation_authority",
        SimpleNamespace(
            active_transcript=active_transcript,
            list_messages=list_messages,
        ),
    )

    response = app_client.get(
        f"/api/v1/conversations/{thread.thread_id}/messages?active_only=true"
    )

    assert response.status_code == 200
    assert captured == {"active": 1, "list": 0}
    assert [item["content"] for item in response.json()["messages"]] == [
        "message-1",
        "answer",
    ]
    assert response.json()["projection"] == "active"


def test_edit_endpoint_creates_new_message_contract(route, app_client, monkeypatch):
    original = _thread()
    edited = _message(original)
    updated = ConversationThread(
        thread_id=original.thread_id,
        tenant_id=original.tenant_id,
        owner_id=original.owner_id,
        created_at=original.created_at,
        updated_at=original.updated_at,
        version=2,
        message_sequence=1,
        active_branch_id=original.active_branch_id,
        state=original.state,
        title=original.title,
        data_class=original.data_class,
    )
    captured = {}

    async def edit_user_message(thread_id, message_id, **kwargs):
        captured.update(
            {"thread_id": thread_id, "message_id": message_id, **kwargs}
        )
        return updated, edited

    monkeypatch.setattr(
        route,
        "conversation_authority",
        SimpleNamespace(edit_user_message=edit_user_message),
    )

    prior = str(uuid4())
    response = app_client.post(
        f"/api/v1/conversations/{original.thread_id}/messages/{prior}/edit",
        json={
            "content": "replacement",
            "idempotency_key": "edit-1",
            "expected_thread_version": 1,
        },
    )

    assert response.status_code == 200
    assert captured["message_id"] == prior
    assert captured["content"] == "replacement"


def test_delete_is_explicit_deletion_intent_not_false_completion(
    route,
    app_client,
    monkeypatch,
):
    original = _thread()
    deleting = ConversationThread(
        thread_id=original.thread_id,
        tenant_id=original.tenant_id,
        owner_id=original.owner_id,
        created_at=original.created_at,
        updated_at=original.updated_at,
        version=2,
        message_sequence=original.message_sequence,
        active_branch_id=original.active_branch_id,
        state=ConversationThreadState.DELETING,
        title=original.title,
        data_class=original.data_class,
    )
    captured = {}

    async def set_state(thread_id, **kwargs):
        captured.update({"thread_id": thread_id, **kwargs})
        return deleting

    monkeypatch.setattr(
        route,
        "conversation_authority",
        SimpleNamespace(set_state=set_state),
    )

    response = app_client.delete(
        f"/api/v1/conversations/{original.thread_id}?expected_thread_version=1"
    )

    assert response.status_code == 200
    assert response.json()["complete"] is False
    assert response.json()["deletion_state"] == "deleting"
    assert captured["state"] is ConversationThreadState.DELETING
