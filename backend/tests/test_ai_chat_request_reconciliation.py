"""Source-level admission contract for governed chat reconciliation.

These checks do not assert live provider access or full AI E2E acceptance.
"""
from uuid import uuid4

import pytest
from pydantic import ValidationError

from routes.ai import AIChatRequest, _chat_request_digest


def _request(**extra):
    data = {
        "message": "Produce a safe original game plan",
        "thread_id": str(uuid4()),
        "idempotency_key": "governed-turn-1",
        "expected_thread_version": 1,
        **extra,
    }
    return AIChatRequest.model_validate(data)


def test_explicit_selection_and_generation_options_survive_validation():
    request = _request(
        provider_id="openai", model_id="configured-model",
        max_output_tokens=2000, temperature=0.25,
        attachment_refs=["chat-attachment://" + "a" * 32],
    )
    assert request.provider_id == "openai"
    assert request.model_id == "configured-model"
    assert request.max_output_tokens == 2000
    assert request.temperature == 0.25
    assert len(request.attachment_refs) == 1


def test_change_of_model_or_attached_evidence_changes_idempotent_turn_digest():
    data = {
        "message": "Give a concise design outline", "thread_id": str(uuid4()),
        "idempotency_key": "same-key", "expected_thread_version": 1,
    }
    original = AIChatRequest.model_validate(data)
    for override in (
        {"provider_id": "openai", "model_id": "configured-model"},
        {"max_output_tokens": 128},
        {"temperature": 0.5},
        {"attachment_refs": ["chat-attachment://" + "b" * 32]},
    ):
        changed = AIChatRequest.model_validate({**data, **override})
        assert _chat_request_digest(original) != _chat_request_digest(changed)


def test_extra_fields_and_oversized_attachments_rejected_not_discarded():
    data = {
        "message": "Hello", "thread_id": str(uuid4()),
        "idempotency_key": "same-key", "expected_thread_version": 1,
    }
    with pytest.raises(ValidationError):
        AIChatRequest.model_validate({**data, "unrecognized_transport_option": True})
    with pytest.raises(ValidationError):
        AIChatRequest.model_validate({**data, "attachment_refs": ["x"] * 5})
    with pytest.raises(ValidationError):
        AIChatRequest.model_validate({**data, "temperature": 100})


@pytest.mark.asyncio
async def test_completed_digest_matched_replay_does_not_need_active_engine(monkeypatch):
    from types import SimpleNamespace
    from routes import ai as ai_routes
    from skeleton.contracts.conversation import ConversationAuthorType

    request = _request()
    user_message = SimpleNamespace(
        author_type=ConversationAuthorType.USER,
        idempotency_key=request.idempotency_key,
        message_id=str(uuid4()),
        attachment_refs=(ai_routes._chat_request_identity_ref(request),),
    )
    reply = SimpleNamespace(
        author_type=ConversationAuthorType.ASSISTANT,
        idempotency_key=request.idempotency_key + ":assistant",
        causal_user_message_id=user_message.message_id,
    )

    async def transcript(*args, **kwargs):
        return [user_message, reply]

    async def replay(thread_id, *, idempotency_key, user):
        assert thread_id == request.thread_id
        assert idempotency_key == request.idempotency_key
        return {"success": True, "terminal": True, "response": "durable reply"}

    def never_call_engine(*args, **kwargs):
        raise AssertionError("Committed replay must not contact engine config")

    monkeypatch.setattr(ai_routes.conversation_authority, "active_transcript", transcript)
    monkeypatch.setattr(ai_routes, "get_ai_chat_turn", replay)
    monkeypatch.setattr(ai_routes.EngineClient, "from_env", never_call_engine)
    result = await ai_routes.ai_chat(
        request, user={"email": "replay@example.org", "tenant_id": "tenant-test"},
    )
    assert result["terminal"] and result["response"] == "durable reply"


@pytest.mark.asyncio
async def test_replay_key_with_changed_request_identity_is_rejected(monkeypatch):
    from types import SimpleNamespace
    from fastapi import HTTPException
    from routes import ai as ai_routes
    from skeleton.contracts.conversation import ConversationAuthorType

    original = _request()
    changed = original.model_copy(update={"message": "Different content"})
    message_id = str(uuid4())
    user_message = SimpleNamespace(
        author_type=ConversationAuthorType.USER,
        idempotency_key=original.idempotency_key, message_id=message_id,
        attachment_refs=(ai_routes._chat_request_identity_ref(original),),
    )
    reply = SimpleNamespace(
        author_type=ConversationAuthorType.ASSISTANT,
        idempotency_key=original.idempotency_key + ":assistant",
        causal_user_message_id=message_id,
    )

    async def transcript(*args, **kwargs):
        return [user_message, reply]

    monkeypatch.setattr(ai_routes.conversation_authority, "active_transcript", transcript)
    with pytest.raises(HTTPException) as error:
        await ai_routes.ai_chat(changed, user={"email": "replay@example.org"})
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_missing_engine_does_not_append_new_user_message(monkeypatch):
    from fastapi import HTTPException
    from routes import ai as ai_routes

    async def transcript(*args, **kwargs):
        return []

    async def forbidden_append(*args, **kwargs):
        raise AssertionError("Never persist a new turn when engine is absent")

    monkeypatch.setattr(ai_routes.conversation_authority, "active_transcript", transcript)
    monkeypatch.setattr(ai_routes.conversation_authority, "append_user_message", forbidden_append)
    monkeypatch.setattr(ai_routes.EngineClient, "from_env", lambda: None)
    with pytest.raises(HTTPException) as error:
        await ai_routes.ai_chat(_request(), user={"email": "new@example.org"})
    assert error.value.status_code == 503
