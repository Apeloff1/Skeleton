from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_chat_binds_ephemeral_context_digest_into_user_idempotency(monkeypatch):
    import routes.gameforge_auth as auth
    import routes.ai as ai

    monkeypatch.setattr(auth, "_enforced", lambda: False)
    captured = {}

    async def active_transcript(*_args, **_kwargs):
        return ()

    async def append_user_message(thread_id, **kwargs):
        captured.update(kwargs)
        raise RuntimeError("stop after append identity capture")

    monkeypatch.setattr(
        ai,
        "conversation_authority",
        SimpleNamespace(
            active_transcript=active_transcript,
            append_user_message=append_user_message,
        ),
    )
    app = FastAPI()
    app.include_router(ai.router)
    with TestClient(app) as client:
        response = client.post(
            "/ai/chat",
            json={
                "message": "question",
                "thread_id": str(uuid4()),
                "idempotency_key": "stable-key",
                "expected_thread_version": 1,
                "context": "same ephemeral code",
            },
        )

    assert response.status_code == 500
    refs = captured["attachment_refs"]
    assert len(refs) == 2
    assert refs[0].startswith("ephemeral-context-sha256:")
    assert len(refs[0].split(":", 1)[1]) == 64
    assert refs[1].startswith("chat-request-sha256:")
    assert len(refs[1].split(":", 1)[1]) == 64



def test_chat_request_identity_binds_context_and_memory_policy_but_not_thread_version():
    import routes.ai as ai

    base = ai.AIChatRequest(
        message="question",
        thread_id=str(uuid4()),
        idempotency_key="stable-key",
        expected_thread_version=1,
        context="same ephemeral code",
        memory_policy=ai.AIChatMemoryPolicy(
            persist_verified_response=True,
            kind="semantic",
            namespace="assistant",
        ),
    )
    stale_retry = ai.AIChatRequest(
        message=base.message,
        thread_id=base.thread_id,
        idempotency_key=base.idempotency_key,
        expected_thread_version=99,
        context=base.context,
        memory_policy=base.memory_policy,
    )
    changed_context = ai.AIChatRequest(
        message=base.message,
        thread_id=base.thread_id,
        idempotency_key=base.idempotency_key,
        expected_thread_version=1,
        context="different ephemeral code",
        memory_policy=base.memory_policy,
    )
    changed_policy = ai.AIChatRequest(
        message=base.message,
        thread_id=base.thread_id,
        idempotency_key=base.idempotency_key,
        expected_thread_version=1,
        context=base.context,
        memory_policy=ai.AIChatMemoryPolicy(
            persist_verified_response=False,
            kind="semantic",
            namespace="assistant",
        ),
    )

    identity = ai._chat_request_identity_ref(base)
    assert identity == ai._chat_request_identity_ref(stale_retry)
    assert identity != ai._chat_request_identity_ref(changed_context)
    assert identity != ai._chat_request_identity_ref(changed_policy)
    assert identity.startswith("chat-request-sha256:")
