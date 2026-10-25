from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from backend.tests.chat_runtime_fixtures import chat_runtime as chat_runtime
from fastapi import HTTPException
from pydantic import ValidationError


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
        user_message=SimpleNamespace(message_id="22222222-2222-2222-2222-222222222222"),
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
        user_message=SimpleNamespace(message_id="22222222-2222-2222-2222-222222222222"),
    )

    assert intent is not None
    assert intent["subject_id"] == "owner-a"
    assert intent["namespace"] == "assistant.preferences"
    assert intent["kind"] == "preference"
    assert intent["content_from"] == "verified_final_output"
    assert intent["idempotency_key"] == (
        "chat-memory:" + request.thread_id + ":22222222-2222-2222-2222-222222222222:preference"
    )
    assert intent["provenance_refs"] == [
        "conversation:" + request.thread_id,
        ("conversation-message:22222222-2222-2222-2222-222222222222"),
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
            user_message=SimpleNamespace(message_id="22222222-2222-2222-2222-222222222222"),
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
            user_message=SimpleNamespace(message_id="22222222-2222-2222-2222-222222222222"),
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
        user_message=SimpleNamespace(message_id="22222222-2222-2222-2222-222222222222"),
    )
    assert intent is not None
    assert intent["expires_at"].tzinfo is not None


@pytest.mark.asyncio
async def test_chat_memory_policy_reaches_delegated_engine_command(chat_runtime):
    h = chat_runtime
    h.engine.memory_refs = ("memory:canonical-1",)
    response = await h.route.ai_chat(
        h.request(
            memory_policy={
                "persist_verified_response": True,
                "kind": "semantic",
                "namespace": "assistant",
            }
        ),
        user=h.user,
    )
    assert response["success"]
    command = h.engine.commands[0]
    intent = command.execution_request.context_policy["memory_write_intent"]
    assert intent["subject_id"] == "owner-a"
    assert intent["namespace"] == "assistant" and intent["kind"] == "semantic"
    assert intent["content_from"] == "verified_final_output"
    assert "engine:memory" in command.delegated_authority.scopes
    assert response["engine_memory_refs"] == ["memory:canonical-1"]
    assert h.transcript()[-1].memory_refs == ("memory:canonical-1",)


@pytest.mark.asyncio
async def test_chat_memory_policy_fails_closed_without_canonical_engine(chat_runtime, monkeypatch):
    h = chat_runtime

    async def forbidden_legacy(*args, **kwargs):
        raise AssertionError("memory opt-in must not activate a legacy provider")

    monkeypatch.setattr(h.route, "call_llm", forbidden_legacy)
    monkeypatch.setattr(h.route.EngineClient, "from_env", lambda: None)
    with pytest.raises(HTTPException) as error:
        await h.route.ai_chat(
            h.request(
                memory_policy={
                    "persist_verified_response": True,
                    "kind": "semantic",
                }
            ),
            user=h.user,
        )
    assert error.value.status_code == 503
    assert error.value.detail["code"] == "engine_unavailable"
    assert h.transcript() == ()
