"""Source-level admission contract for governed chat reconciliation.

These checks do not assert live provider access or full AI E2E acceptance.
"""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from skeleton.contracts.conversation import (
    ConversationAuthorType,
    ConversationMessage,
    ConversationThread,
    ConversationThreadState,
)
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


def _canonical_completed_turn(request, *, tenant_id: str, owner_id: str):
    """Build real immutable conversation records, not a duck-typed replay stub."""
    from routes import ai as route

    stamp = datetime.now(timezone.utc)
    branch_id = str(uuid4())
    user_message = ConversationMessage(
        message_id=str(uuid4()),
        thread_id=request.thread_id,
        branch_id=branch_id,
        sequence=1,
        author_type=ConversationAuthorType.USER,
        created_at=stamp,
        idempotency_key=request.idempotency_key,
        content=request.message,
        attachment_refs=(route._chat_request_identity_ref(request),),
        data_class="internal",
    )
    assistant_message = ConversationMessage(
        message_id=str(uuid4()),
        thread_id=request.thread_id,
        branch_id=branch_id,
        sequence=2,
        author_type=ConversationAuthorType.ASSISTANT,
        created_at=stamp,
        idempotency_key=request.idempotency_key + ":assistant",
        content="durable reply",
        parent_message_id=user_message.message_id,
        causal_user_message_id=user_message.message_id,
        operation_id=route._chat_turn_ids(request.thread_id, user_message.message_id)[0],
        ai_result_id="engine-result:" + route._chat_turn_ids(request.thread_id, user_message.message_id)[1],
        data_class="internal",
    )
    thread = ConversationThread(
        thread_id=request.thread_id,
        tenant_id=tenant_id,
        owner_id=owner_id,
        created_at=stamp,
        updated_at=stamp,
        version=2,
        message_sequence=2,
        active_branch_id=branch_id,
        state=ConversationThreadState.ACTIVE,
        title="Durable replay",
        data_class="internal",
    )
    return thread, user_message, assistant_message


@pytest.mark.asyncio
async def test_completed_digest_matched_replay_does_not_need_active_engine(monkeypatch):
    from routes import ai as ai_routes

    request = _request()
    thread, user_message, reply = _canonical_completed_turn(
        request, tenant_id="tenant-test", owner_id="replay@example.org",
    )

    async def transcript(*_args, **_kwargs):
        return (user_message, reply)

    async def get_thread(*_args, **_kwargs):
        return thread

    def never_call_engine(*_args, **_kwargs):
        raise AssertionError("Committed replay must not contact engine config")

    async def persisted_request_refs(*_args, **_kwargs):
        # Request identity is read from its canonical persisted record, not
        # from an unrelated Mongo collection in this isolated test.
        return user_message.attachment_refs

    monkeypatch.setattr(ai_routes.conversation_authority, "active_transcript", transcript)
    monkeypatch.setattr(ai_routes.conversation_authority, "get_thread", get_thread)
    monkeypatch.setattr(ai_routes.conversation_authority, "user_request_refs", persisted_request_refs)
    monkeypatch.setattr(ai_routes.EngineClient, "from_env", never_call_engine)

    result = await ai_routes.ai_chat(
        request, user={"email": "replay@example.org", "tenant_id": "tenant-test"},
    )
    assert result["replayed"] is True
    assert result["response"] == "durable reply"
    assert result["success"] is True


@pytest.mark.asyncio
async def test_replay_key_with_changed_request_identity_is_rejected(monkeypatch):
    from fastapi import HTTPException
    from routes import ai as ai_routes

    original = _request()
    changed = original.model_copy(update={"message": "Different content"})
    thread, user_message, reply = _canonical_completed_turn(
        original, tenant_id="default", owner_id="replay@example.org",
    )

    async def transcript(*_args, **_kwargs):
        return (user_message, reply)

    async def get_thread(*_args, **_kwargs):
        return thread

    async def persisted_request_refs(*_args, **_kwargs):
        return user_message.attachment_refs

    monkeypatch.setattr(ai_routes.conversation_authority, "active_transcript", transcript)
    monkeypatch.setattr(ai_routes.conversation_authority, "get_thread", get_thread)
    monkeypatch.setattr(ai_routes.conversation_authority, "user_request_refs", persisted_request_refs)
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


# Consumer runtime regression scenarios retain shared durable authority
# alongside upstream receipt-aware fixtures. Their helpers remain independent.


def _completed_turn(request):
    from datetime import datetime, timezone
    from skeleton.contracts.conversation import ConversationAuthorType, ConversationMessage, ConversationThread, ConversationThreadState
    from routes import ai as ai_routes
    now = datetime.now(timezone.utc)
    branch = str(uuid4())
    user = ConversationMessage(message_id=str(uuid4()), thread_id=request.thread_id, branch_id=branch, sequence=1, author_type=ConversationAuthorType.USER, created_at=now, idempotency_key=request.idempotency_key, content=request.message, attachment_refs=(ai_routes._chat_request_identity_ref(request),))
    reply = ConversationMessage(message_id=str(uuid4()), thread_id=request.thread_id, branch_id=branch, sequence=2, author_type=ConversationAuthorType.ASSISTANT, created_at=now, idempotency_key=request.idempotency_key + ':assistant', content='durable reply', parent_message_id=user.message_id, causal_user_message_id=user.message_id, operation_id=str(uuid4()), ai_result_id='engine-result:durable-replay')
    thread = ConversationThread(thread_id=request.thread_id, tenant_id='tenant-test', owner_id='replay@example.org', created_at=now, updated_at=now, version=3, message_sequence=2, active_branch_id=branch, state=ConversationThreadState.ACTIVE)
    return (thread, user, reply)


@pytest.mark.asyncio
async def test_completed_digest_matched_replay_does_not_need_active_engine_consumer_runtime(monkeypatch):
    from routes import ai as ai_routes
    request = _request()
    thread, user_message, reply = _completed_turn(request)

    async def transcript(*args, **kwargs):
        return [user_message, reply]

    async def get_thread(*args, **kwargs):
        return thread

    async def refs(*args, **kwargs):
        return user_message.attachment_refs

    def never_call_engine(*args, **kwargs):
        raise AssertionError('Committed replay must not contact engine config')
    monkeypatch.setattr(ai_routes.conversation_authority, 'active_transcript', transcript)
    monkeypatch.setattr(ai_routes.conversation_authority, 'get_thread', get_thread)
    monkeypatch.setattr(ai_routes.conversation_authority, 'user_request_refs', refs)
    monkeypatch.setattr(ai_routes.EngineClient, 'from_env', never_call_engine)
    result = await ai_routes.ai_chat(request, user={'email': 'replay@example.org', 'tenant_id': 'tenant-test'})
    assert result['success'] and result['replayed'] and (result['response'] == 'durable reply')


@pytest.mark.asyncio
async def test_replay_key_with_changed_request_identity_is_rejected_consumer_runtime(monkeypatch):
    from fastapi import HTTPException
    from routes import ai as ai_routes
    original = _request()
    changed = original.model_copy(update={'message': 'Different content'})
    _, user_message, reply = _completed_turn(original)

    async def transcript(*args, **kwargs):
        return [user_message, reply]

    async def refs(*args, **kwargs):
        return user_message.attachment_refs
    monkeypatch.setattr(ai_routes.conversation_authority, 'active_transcript', transcript)
    monkeypatch.setattr(ai_routes.conversation_authority, 'user_request_refs', refs)
    with pytest.raises(HTTPException) as error:
        await ai_routes.ai_chat(changed, user={'email': 'replay@example.org'})
    assert error.value.status_code == 409
