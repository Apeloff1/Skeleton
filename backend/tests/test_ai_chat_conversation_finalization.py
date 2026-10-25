from __future__ import annotations

import pytest
from backend.tests.chat_runtime_fixtures import chat_runtime as chat_runtime
from fastapi import HTTPException

from core.conversations import ConversationStorageUnavailable
from core.engine_client import EngineUnavailableError


@pytest.mark.asyncio
async def test_chat_commits_assistant_only_from_successful_engine_result(chat_runtime):
    h = chat_runtime
    response = await h.route.ai_chat(h.request(), user=h.user)
    user, assistant = h.transcript()
    command = h.engine.commands[0]
    assert response["success"] and assistant.content == h.engine.output
    assert assistant.causal_user_message_id == user.message_id
    assert assistant.operation_id == command.operation.operation_id
    assert assistant.ai_result_id == "engine-result:" + command.execution_request.execution_id
    assert assistant.provider_receipt_refs == h.engine.provider_receipts
    assert assistant.context_source_snapshot == command.compiled_context.source_snapshot


@pytest.mark.asyncio
async def test_chat_never_commits_assistant_when_engine_is_unavailable(chat_runtime):
    h = chat_runtime
    h.engine.submit_error = EngineUnavailableError("unavailable")
    response = await h.route.ai_chat(h.request(), user=h.user)
    assert response["success"] is False
    assert len(h.transcript()) == 1
    assert h.transcript()[0].author_type.value == "user"


@pytest.mark.asyncio
async def test_chat_retry_after_assistant_commit_failure_preserves_engine_identity(chat_runtime, monkeypatch):
    h = chat_runtime
    commit = h.authority.commit_assistant_message
    attempts = 0

    async def fail_once(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ConversationStorageUnavailable("simulated commit outage")
        return await commit(*args, **kwargs)

    monkeypatch.setattr(h.authority, "commit_assistant_message", fail_once)
    with pytest.raises(HTTPException) as error:
        await h.route.ai_chat(h.request(), user=h.user)
    assert error.value.status_code == 503
    original = h.engine.commands[0]
    assert len(h.transcript()) == 1
    recovered = await h.route.ai_chat(h.request(), user=h.user)
    assert recovered["success"]
    assert len(h.engine.commands) == 1
    assert h.transcript()[-1].operation_id == original.operation.operation_id
    assert h.transcript()[-1].ai_result_id == "engine-result:" + original.execution_request.execution_id


@pytest.mark.asyncio
async def test_chat_blocks_different_turn_while_prior_user_turn_is_incomplete(chat_runtime):
    h = chat_runtime
    h.engine.complete_on_submit = False
    await h.route.ai_chat(h.request(response_mode="deferred"), user=h.user)
    with pytest.raises(HTTPException) as error:
        await h.route.ai_chat(
            h.request(idempotency_key="turn-2", message="New work", expected_thread_version=2), user=h.user
        )
    assert error.value.status_code == 409
    assert len(h.engine.commands) == 1 and len(h.transcript()) == 1
