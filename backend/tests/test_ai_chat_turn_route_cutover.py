from __future__ import annotations

import pytest
from backend.tests.chat_runtime_fixtures import chat_runtime as chat_runtime
from fastapi import HTTPException
from skeleton.ai.assistant.turn_runtime import TurnState

from core.engine_client import EngineUnavailableError


@pytest.mark.asyncio
async def test_live_chat_success_reaches_durable_complete(chat_runtime, ai_chat_turn_test_authority):
    h = chat_runtime
    result = await h.route.ai_chat(h.request(), user=h.user)
    assert result["success"] and result["turn_state"] == "complete"
    receipt = result["response_acceptance_receipt"]
    assert receipt.startswith("response-acceptance-sha256:")
    assert receipt in h.transcript()[-1].artifact_refs
    persisted = ai_chat_turn_test_authority.repo.reconstruct(
        result["operation_id"], tenant_id="tenant-a", owner_id="owner-a"
    )
    assert persisted.snapshot.state is TurnState.COMPLETE
    events = ai_chat_turn_test_authority.repo.list_events(
        result["operation_id"], tenant_id="tenant-a", owner_id="owner-a"
    )
    assert [event.to_state for event in events] == [
        TurnState.ADMITTED,
        TurnState.USER_MESSAGE_COMMITTED,
        TurnState.CONTEXT_COMPILING,
        TurnState.ROUTING,
        TurnState.MODEL_RUNNING,
        TurnState.VERIFYING,
        TurnState.FINALIZING,
        TurnState.ASSISTANT_MESSAGE_COMMITTED,
        TurnState.COMPLETE,
    ]
    finalizing = next(event for event in events if event.to_state is TurnState.FINALIZING)
    assert finalizing.provider_receipt_ref.startswith("provider-set-sha256:")
    assert "provider:test:" not in finalizing.provider_receipt_ref
    ownership = ai_chat_turn_test_authority.repo.list_ownership_receipts(
        result["operation_id"], tenant_id="tenant-a", owner_id="owner-a"
    )
    assert [receipt["action"] for receipt in ownership] == ["acquire", "renew", "renew", "release"]
    assert [receipt["epoch"] for receipt in ownership] == [1, 1, 1, 1]
    for previous, current in zip(ownership, ownership[1:]):
        assert current["previous_receipt_digest"] == previous["digest"]


@pytest.mark.asyncio
async def test_live_chat_engine_outage_resumes_same_operation_to_completion(chat_runtime):
    h = chat_runtime
    h.engine.submit_error = EngineUnavailableError("offline")
    first = await h.route.ai_chat(h.request(), user=h.user)
    assert first["success"] is False
    assert len(h.transcript()) == 1
    original = h.engine.commands[0].as_dict()
    h.engine.submit_error = None
    second = await h.route.ai_chat(h.request(), user=h.user)
    assert second["success"]
    if second.get("response") is None:
        second = await h.route.get_ai_chat_turn(h.thread.thread_id, idempotency_key="turn-1", user=h.user)
    assert second["response"] == h.engine.output
    assert h.engine.commands[-1].as_dict() == original
    assert len(h.transcript()) == 2


@pytest.mark.asyncio
async def test_live_chat_event_page_supports_digest_bound_reconnect(chat_runtime):
    h = chat_runtime
    await h.route.ai_chat(h.request(), user=h.user)
    page = await h.route.get_ai_chat_turn_events(
        h.thread.thread_id, idempotency_key="turn-1", after_sequence=0, last_event_digest=None, limit=2, user=h.user
    )
    assert len(page["events"]) == 2
    last = page["cursor"]
    resumed = await h.route.get_ai_chat_turn_events(
        h.thread.thread_id,
        idempotency_key="turn-1",
        after_sequence=last["last_seen_sequence"],
        last_event_digest=last["last_event_digest"],
        limit=100,
        user=h.user,
    )
    assert [event["sequence"] for event in resumed["events"]] == list(range(3, 10))
    assert resumed["events"][-1]["kind"] == "turn.completed"
    assert len(resumed["page_digest"]) == 64
    with pytest.raises(HTTPException) as error:
        await h.route.get_ai_chat_turn_events(
            h.thread.thread_id,
            idempotency_key="turn-1",
            after_sequence=last["last_seen_sequence"],
            last_event_digest="f" * 64,
            limit=100,
            user=h.user,
        )
    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_cancellation_request_does_not_fabricate_terminal_cancelled(chat_runtime, ai_chat_turn_test_authority):
    h = chat_runtime
    h.engine.complete_on_submit = False
    result = await h.route.ai_chat(h.request(response_mode="deferred"), user=h.user)
    cancelled = await h.route.cancel_ai_chat_turn(
        h.thread.thread_id, h.route.AIChatCancelRequest(idempotency_key="turn-1"), user=h.user
    )
    assert cancelled["cancellation_requested"] is True
    assert h.engine.cancelled == [result["engine_execution_id"]]
    persisted = ai_chat_turn_test_authority.repo.reconstruct(
        result["operation_id"], tenant_id="tenant-a", owner_id="owner-a"
    )
    assert persisted.snapshot.state is not TurnState.CANCELLED
    assert len(h.transcript()) == 1


@pytest.mark.asyncio
async def test_live_owner_prevents_duplicate_engine_execution(chat_runtime, ai_chat_turn_test_authority):
    h = chat_runtime
    request = h.request(response_mode="deferred")
    message, metadata = await h.route._prepare_new_chat_execution(
        request,
        h.user,
        thread=h.thread,
        transcript=(),
        tenant_id="tenant-a",
        owner_id="owner-a",
        attachment_refs=h.route._chat_context_attachment_refs(
            request, h.route._chat_request_digest(request), include_prepared=True
        ),
    )
    thread, message = await h.authority.append_message(
        message,
        tenant_id="tenant-a",
        owner_id="owner-a",
        expected_thread_version=1,
        execution_metadata=metadata,
    )
    operation_id, _execution_id = h.route._chat_turn_ids(thread.thread_id, message.message_id)
    turn = await h.route.chat_turn_lifecycle.begin(
        thread=thread,
        user_message=message,
        operation_id=operation_id,
        request_digest=h.route._chat_request_digest(request),
        tenant_id="tenant-a",
        owner_id="owner-a",
    )
    lease = await h.route.chat_turn_lifecycle.acquire_execution(
        turn, tenant_id="tenant-a", owner_id="owner-a", holder_id="existing-worker", ttl_seconds=60
    )
    replay = await h.route.ai_chat(request, user=h.user)
    assert replay["terminal"] is False and replay["state"] == "admission_in_progress"
    assert replay["operation_id"] == operation_id and h.engine.commands == []
    retained = ai_chat_turn_test_authority.repo.assert_lease(lease)
    assert retained.holder_id == "existing-worker" and retained.epoch == 1
    await h.route.chat_turn_lifecycle.release_execution(lease)


@pytest.mark.asyncio
async def test_live_chat_rejects_unaccepted_engine_output_before_transcript_commit(
    chat_runtime, ai_chat_turn_test_authority
):
    h = chat_runtime
    h.engine.verification = "unverified"
    result = await h.route.ai_chat(h.request(), user=h.user)
    assert result["success"] is False and result["error_code"] == "response_acceptance_rejected"
    assert "verification_not_accepted" in result["response_acceptance_reasons"]
    assert all(message.content != h.engine.output for message in h.transcript())
    assert "chat-terminal:failed" in h.transcript()[-1].artifact_refs
    persisted = ai_chat_turn_test_authority.repo.reconstruct(
        result["operation_id"], tenant_id="tenant-a", owner_id="owner-a"
    )
    assert persisted.snapshot.state is TurnState.FAILED_TERMINAL


@pytest.mark.asyncio
async def test_deferred_poll_rejects_unaccepted_engine_output_before_commit(chat_runtime, ai_chat_turn_test_authority):
    h = chat_runtime
    h.engine.complete_on_submit = False
    admitted = await h.route.ai_chat(h.request(response_mode="deferred"), user=h.user)
    h.engine.verification = "unverified"
    h.engine.complete()
    result = await h.route.get_ai_chat_turn(h.thread.thread_id, idempotency_key="turn-1", user=h.user)
    assert result["success"] is False and result["failure_code"] == "response_acceptance_rejected"
    assert all(message.content != h.engine.output for message in h.transcript())
    assert "chat-terminal:failed" in h.transcript()[-1].artifact_refs
    persisted = ai_chat_turn_test_authority.repo.reconstruct(
        admitted["operation_id"], tenant_id="tenant-a", owner_id="owner-a"
    )
    assert persisted.snapshot.state is TurnState.FAILED_TERMINAL
