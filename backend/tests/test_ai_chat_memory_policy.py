from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
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
