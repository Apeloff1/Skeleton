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

    async def append_user_message(thread_id, **kwargs):
        captured.update(kwargs)
        raise RuntimeError("stop after append identity capture")

    monkeypatch.setattr(
        ai,
        "conversation_authority",
        SimpleNamespace(append_user_message=append_user_message),
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
    assert len(refs) == 1
    assert refs[0].startswith("ephemeral-context-sha256:")
    assert len(refs[0].split(":", 1)[1]) == 64
