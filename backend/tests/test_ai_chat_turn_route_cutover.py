from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from core.engine_client import EngineNotFoundError, EngineUnavailableError
from skeleton.ai.assistant.turn_runtime import TurnState
from skeleton.contracts.conversation import (
    ConversationAuthorType,
    ConversationMessage,
    ConversationThread,
    ConversationThreadState,
)


NOW = datetime(2026, 10, 6, 4, 0, tzinfo=timezone.utc)


def _thread_and_user():
    thread_id = str(uuid4())
    branch_id = str(uuid4())
    thread = ConversationThread(
        thread_id=thread_id,
        tenant_id="tenant-a",
        owner_id="owner-a",
        created_at=NOW,
        updated_at=NOW,
        version=2,
        message_sequence=1,
        active_branch_id=branch_id,
        state=ConversationThreadState.ACTIVE,
        title="Durable chat",
        data_class="internal",
    )
    user = ConversationMessage(
        message_id=str(uuid4()),
        thread_id=thread_id,
        branch_id=branch_id,
        sequence=1,
        author_type=ConversationAuthorType.USER,
        created_at=NOW,
        idempotency_key="turn-1",
        content="Build it.",
        data_class="internal",
    )
    return thread, user


def _request(route, thread_id):
    return route.AIChatRequest(
        message="Build it.",
        thread_id=thread_id,
        idempotency_key="turn-1",
        expected_thread_version=1,
    )


def _conversation_authority(thread, user, *, allow_commit=True):
    async def active_transcript(*_args, **_kwargs):
        return (user,)

    async def append_user_message(*_args, **_kwargs):
        return thread, user

    async def get_thread(*_args, **_kwargs):
        return thread

    async def commit_assistant_message(_thread_id, **kwargs):
        if not allow_commit:
            raise AssertionError("assistant commit must not run")
        committed_thread = ConversationThread(
            thread_id=thread.thread_id,
            tenant_id=thread.tenant_id,
            owner_id=thread.owner_id,
            created_at=thread.created_at,
            updated_at=thread.updated_at,
            version=3,
            message_sequence=2,
            active_branch_id=thread.active_branch_id,
            state=thread.state,
            title=thread.title,
            data_class=thread.data_class,
        )
        message = ConversationMessage(
            message_id=str(uuid4()),
            thread_id=thread.thread_id,
            branch_id=thread.active_branch_id,
            sequence=2,
            author_type=ConversationAuthorType.ASSISTANT,
            created_at=NOW,
            idempotency_key=kwargs["idempotency_key"],
            content=kwargs["content"],
            parent_message_id=user.message_id,
            causal_user_message_id=user.message_id,
            operation_id=kwargs["operation_id"],
            ai_result_id=kwargs["ai_result_id"],
            context_id=kwargs["context_id"],
            context_digest=kwargs["context_digest"],
            context_source_snapshot=kwargs["context_source_snapshot"],
            context_compiler_version=kwargs["context_compiler_version"],
            provider_receipt_refs=kwargs.get("provider_receipt_refs", ()),
            tool_receipt_refs=kwargs.get("tool_receipt_refs", ()),
            memory_refs=kwargs.get("memory_refs", ()),
            citation_refs=kwargs.get("citation_refs", ()),
            artifact_refs=kwargs.get("artifact_refs", ()),
            data_class=thread.data_class,
        )
        return committed_thread, message

    return SimpleNamespace(
        active_transcript=active_transcript,
        append_user_message=append_user_message,
        get_thread=get_thread,
        commit_assistant_message=commit_assistant_message,
    )


@pytest.mark.asyncio
async def test_live_chat_success_reaches_durable_complete(
    monkeypatch,
    ai_chat_turn_test_authority,
):
    import routes.ai as route

    thread, user = _thread_and_user()
    monkeypatch.setattr(
        route,
        "conversation_authority",
        _conversation_authority(thread, user),
    )
    fake_client = SimpleNamespace(
        config=SimpleNamespace(
            service_principal="codedock-backend",
            execution_timeout_s=30.0,
        )
    )

    async def wait_for_terminal(**_kwargs):
        raise EngineNotFoundError("not started")

    async def execute(command):
        return SimpleNamespace(
            operation_id=command.operation.operation_id,
            final_output="Done.",
            execution_id=command.execution_request.execution_id,
            verification="verified",
            evidence_refs=("evidence:1",),
            provider_receipts=("provider:test:receipt-1",),
            tool_receipts=(),
            memory_refs=(),
            artifact_refs=(),
        )

    fake_client.wait_for_terminal = wait_for_terminal
    fake_client.execute = execute
    monkeypatch.setattr(route.EngineClient, "from_env", lambda: fake_client)

    response = await route.ai_chat(
        _request(route, thread.thread_id),
        user={"tenant_id": "tenant-a", "email": "owner-a"},
    )

    assert response["success"] is True
    assert response["turn_state"] == "complete"
    assert response["response_acceptance_receipt"].startswith(
        "response-acceptance-sha256:"
    )
    assert response["response_acceptance_receipt"] in (
        response["assistant_message"]["artifact_refs"]
    )
    persisted = ai_chat_turn_test_authority.repo.reconstruct(
        response["operation_id"],
        tenant_id="tenant-a",
        owner_id="owner-a",
    )
    assert persisted.snapshot.state is TurnState.COMPLETE
    events = ai_chat_turn_test_authority.repo.list_events(
        response["operation_id"],
        tenant_id="tenant-a",
        owner_id="owner-a",
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

    ownership = ai_chat_turn_test_authority.repo.list_ownership_receipts(
        response["operation_id"],
        tenant_id="tenant-a",
        owner_id="owner-a",
    )
    assert [receipt["action"] for receipt in ownership] == [
        "acquire",
        "renew",
        "renew",
        "release",
    ]
    assert [receipt["epoch"] for receipt in ownership] == [1, 1, 1, 1]
    assert ownership[1]["previous_receipt_digest"] == ownership[0]["digest"]
    assert ownership[2]["previous_receipt_digest"] == ownership[1]["digest"]
    assert ownership[3]["previous_receipt_digest"] == ownership[2]["digest"]


@pytest.mark.asyncio
async def test_live_chat_engine_outage_resumes_same_operation_to_completion(
    monkeypatch,
    ai_chat_turn_test_authority,
):
    import routes.ai as route

    thread, user = _thread_and_user()
    monkeypatch.setattr(
        route,
        "conversation_authority",
        _conversation_authority(thread, user),
    )
    fake_client = SimpleNamespace(
        config=SimpleNamespace(
            service_principal="codedock-backend",
            execution_timeout_s=30.0,
        )
    )
    attempts = {"execute": 0}

    async def wait_for_terminal(**_kwargs):
        raise EngineNotFoundError("not started")

    async def execute(command):
        attempts["execute"] += 1
        if attempts["execute"] == 1:
            raise EngineUnavailableError("down")
        return SimpleNamespace(
            final_output="Recovered.",
            execution_id=command.execution_request.execution_id,
            verification="verified",
            evidence_refs=(),
            provider_receipts=("provider:test:recovered",),
            tool_receipts=(),
            memory_refs=(),
            artifact_refs=(),
        )

    fake_client.wait_for_terminal = wait_for_terminal
    fake_client.execute = execute
    monkeypatch.setattr(route.EngineClient, "from_env", lambda: fake_client)

    first = await route.ai_chat(
        _request(route, thread.thread_id),
        user={"tenant_id": "tenant-a", "email": "owner-a"},
    )

    assert first["success"] is False
    assert first["error_code"] == "engine_unavailable"
    operation_id, _ = route._chat_turn_ids(thread.thread_id, user.message_id)
    after_outage = ai_chat_turn_test_authority.repo.reconstruct(
        operation_id,
        tenant_id="tenant-a",
        owner_id="owner-a",
    )
    assert after_outage.snapshot.state is TurnState.MODEL_RUNNING
    assert after_outage.snapshot.terminal is False
    outage_digest = after_outage.snapshot.last_event_digest

    second = await route.ai_chat(
        _request(route, thread.thread_id),
        user={"tenant_id": "tenant-a", "email": "owner-a"},
    )

    assert second["success"] is True
    assert second["response"] == "Recovered."
    assert second["operation_id"] == operation_id
    assert second["turn_state"] == "complete"
    recovered = ai_chat_turn_test_authority.repo.reconstruct(
        operation_id,
        tenant_id="tenant-a",
        owner_id="owner-a",
    )
    assert recovered.snapshot.state is TurnState.COMPLETE
    assert recovered.snapshot.last_event_digest != outage_digest
    assert attempts["execute"] == 2

    retry_lease = ai_chat_turn_test_authority.repo.acquire_lease(
        operation_id,
        tenant_id="tenant-a",
        owner_id="owner-a",
        holder_id="retry-worker",
        ttl_seconds=30,
    )
    assert retry_lease.epoch == 2
    ownership = ai_chat_turn_test_authority.repo.list_ownership_receipts(
        operation_id,
        tenant_id="tenant-a",
        owner_id="owner-a",
    )
    assert [receipt["action"] for receipt in ownership] == [
        "acquire",
        "release",
        "takeover",
    ]
    ai_chat_turn_test_authority.repo.release_lease(retry_lease)


@pytest.mark.asyncio
async def test_live_chat_event_page_supports_digest_bound_reconnect(
    monkeypatch,
    ai_chat_turn_test_authority,
):
    import routes.ai as route

    thread, user = _thread_and_user()
    authority = _conversation_authority(thread, user)
    monkeypatch.setattr(route, "conversation_authority", authority)
    fake_client = SimpleNamespace(
        config=SimpleNamespace(
            service_principal="codedock-backend",
            execution_timeout_s=30.0,
        )
    )

    async def wait_for_terminal(**_kwargs):
        raise EngineNotFoundError("not started")

    async def execute(command):
        return SimpleNamespace(
            operation_id=command.operation.operation_id,
            final_output="Done.",
            execution_id=command.execution_request.execution_id,
            verification="verified",
            evidence_refs=(),
            provider_receipts=("provider:test:receipt-1",),
            tool_receipts=(),
            memory_refs=(),
            artifact_refs=(),
        )

    fake_client.wait_for_terminal = wait_for_terminal
    fake_client.execute = execute
    monkeypatch.setattr(route.EngineClient, "from_env", lambda: fake_client)

    response = await route.ai_chat(
        _request(route, thread.thread_id),
        user={"tenant_id": "tenant-a", "email": "owner-a"},
    )
    page1 = await route.get_ai_chat_turn_events(
        thread.thread_id,
        idempotency_key="turn-1",
        after_sequence=0,
        last_event_digest=None,
        limit=4,
        user={"tenant_id": "tenant-a", "email": "owner-a"},
    )
    assert page1["success"] is True
    assert page1["operation_id"] == response["operation_id"]
    assert [item["sequence"] for item in page1["events"]] == [1, 2, 3, 4]
    assert page1["terminal"] is True

    cursor = page1["cursor"]
    page2 = await route.get_ai_chat_turn_events(
        thread.thread_id,
        idempotency_key="turn-1",
        after_sequence=cursor["last_seen_sequence"],
        last_event_digest=cursor["last_event_digest"],
        limit=100,
        user={"tenant_id": "tenant-a", "email": "owner-a"},
    )
    assert [item["sequence"] for item in page2["events"]] == [5, 6, 7, 8, 9]
    assert page2["events"][-1]["kind"] == "turn.completed"
    assert len(page2["page_digest"]) == 64

    with pytest.raises(Exception):
        await route.get_ai_chat_turn_events(
            thread.thread_id,
            idempotency_key="turn-1",
            after_sequence=4,
            last_event_digest="b" * 64,
            limit=100,
            user={"tenant_id": "tenant-a", "email": "owner-a"},
        )



@pytest.mark.asyncio
async def test_cancellation_request_does_not_fabricate_terminal_cancelled(
    monkeypatch,
    ai_chat_turn_test_authority,
):
    import routes.ai as route

    thread, user = _thread_and_user()
    monkeypatch.setattr(
        route,
        "conversation_authority",
        _conversation_authority(thread, user, allow_commit=False),
    )

    operation_id, _execution_id = route._chat_turn_ids(
        thread.thread_id,
        user.message_id,
    )
    turn = await route.chat_turn_lifecycle.begin(
        thread=thread,
        user_message=user,
        operation_id=operation_id,
        request_digest=route._chat_request_digest(
            _request(route, thread.thread_id)
        ),
        tenant_id="tenant-a",
        owner_id="owner-a",
    )
    await route.chat_turn_lifecycle.advance(
        turn,
        TurnState.MODEL_RUNNING,
        tenant_id="tenant-a",
        owner_id="owner-a",
        reason_code="engine-running",
    )

    fake_client = SimpleNamespace()

    async def cancel(*_args, **_kwargs):
        return {
            "execution_state": "running",
            "cancellation_requested": True,
        }

    fake_client.cancel = cancel
    monkeypatch.setattr(route.EngineClient, "from_env", lambda: fake_client)

    response = await route.cancel_ai_chat_turn(
        thread.thread_id,
        route.AIChatCancelRequest(
            idempotency_key="turn-1",
            reason="user_cancelled",
        ),
        user={"tenant_id": "tenant-a", "email": "owner-a"},
    )

    assert response["success"] is True
    assert response["changed"] is True
    assert response["terminal"] is False
    assert response["state"] == "cancellation_requested"
    assert response["turn_state"] == "model_running"

    persisted = ai_chat_turn_test_authority.repo.reconstruct(
        operation_id,
        tenant_id="tenant-a",
        owner_id="owner-a",
    )
    assert persisted.snapshot.state is TurnState.MODEL_RUNNING


@pytest.mark.asyncio
async def test_live_owner_prevents_duplicate_engine_execution(
    monkeypatch,
    ai_chat_turn_test_authority,
):
    import routes.ai as route

    thread, user = _thread_and_user()
    monkeypatch.setattr(
        route,
        "conversation_authority",
        _conversation_authority(thread, user, allow_commit=False),
    )
    operation_id, _execution_id = route._chat_turn_ids(
        thread.thread_id,
        user.message_id,
    )
    turn = await route.chat_turn_lifecycle.begin(
        thread=thread,
        user_message=user,
        operation_id=operation_id,
        request_digest=route._chat_request_digest(
            _request(route, thread.thread_id)
        ),
        tenant_id="tenant-a",
        owner_id="owner-a",
    )
    lease = await route.chat_turn_lifecycle.acquire_execution(
        turn,
        tenant_id="tenant-a",
        owner_id="owner-a",
        holder_id="existing-worker",
        ttl_seconds=60,
    )

    calls = {"execute": 0}
    fake_client = SimpleNamespace(
        config=SimpleNamespace(
            service_principal="codedock-backend",
            execution_timeout_s=30.0,
        )
    )

    async def wait_for_terminal(**_kwargs):
        raise EngineNotFoundError("not started")

    async def execute(_command):
        calls["execute"] += 1
        raise AssertionError("competing route must not execute the engine")

    fake_client.wait_for_terminal = wait_for_terminal
    fake_client.execute = execute
    monkeypatch.setattr(route.EngineClient, "from_env", lambda: fake_client)

    response = await route.ai_chat(
        _request(route, thread.thread_id),
        user={"tenant_id": "tenant-a", "email": "owner-a"},
    )
    assert response["success"] is True
    assert response["accepted"] is True
    assert response["terminal"] is False
    assert response["state"] == "execution_in_progress"
    assert response["operation_id"] == operation_id
    assert calls["execute"] == 0

    current = ai_chat_turn_test_authority.repo.assert_lease(lease)
    assert current.holder_id == "existing-worker"
    assert current.epoch == 1



@pytest.mark.asyncio
async def test_live_chat_rejects_unaccepted_engine_output_before_transcript_commit(
    monkeypatch,
    ai_chat_turn_test_authority,
):
    import routes.ai as route

    thread, user = _thread_and_user()
    monkeypatch.setattr(
        route,
        "conversation_authority",
        _conversation_authority(thread, user, allow_commit=False),
    )
    fake_client = SimpleNamespace(
        config=SimpleNamespace(
            service_principal="codedock-backend",
            execution_timeout_s=30.0,
        )
    )

    async def wait_for_terminal(**_kwargs):
        raise EngineNotFoundError("not started")

    async def execute(command):
        return SimpleNamespace(
            operation_id=command.operation.operation_id,
            final_output="This must never be committed.",
            execution_id=command.execution_request.execution_id,
            verification="unverified",
            evidence_refs=("evidence:rejected",),
            provider_receipts=("provider:test:rejected",),
            tool_receipts=(),
            memory_refs=(),
            artifact_refs=(),
        )

    fake_client.wait_for_terminal = wait_for_terminal
    fake_client.execute = execute
    monkeypatch.setattr(route.EngineClient, "from_env", lambda: fake_client)

    response = await route.ai_chat(
        _request(route, thread.thread_id),
        user={"tenant_id": "tenant-a", "email": "owner-a"},
    )

    assert response["success"] is False
    assert response["error_code"] == "response_acceptance_rejected"
    assert response["response_acceptance_receipt"].startswith(
        "response-acceptance-sha256:"
    )
    assert "verification_not_accepted" in (
        response["response_acceptance_reasons"]
    )
    persisted = ai_chat_turn_test_authority.repo.reconstruct(
        response["operation_id"],
        tenant_id="tenant-a",
        owner_id="owner-a",
    )
    assert persisted.snapshot.state is TurnState.FAILED_TERMINAL
    events = ai_chat_turn_test_authority.repo.list_events(
        response["operation_id"],
        tenant_id="tenant-a",
        owner_id="owner-a",
    )
    assert events[-1].to_state is TurnState.FAILED_TERMINAL
    assert events[-1].reason_code.startswith(
        "response-acceptance-rejected:"
    )



@pytest.mark.asyncio
async def test_deferred_poll_rejects_unaccepted_engine_output_before_commit(
    monkeypatch,
    ai_chat_turn_test_authority,
):
    import routes.ai as route

    thread, user = _thread_and_user()
    operation_id, execution_id = route._chat_turn_ids(
        thread.thread_id,
        user.message_id,
    )
    request = _request(route, thread.thread_id)
    turn = await route.chat_turn_lifecycle.begin(
        thread=thread,
        user_message=user,
        operation_id=operation_id,
        request_digest=route._chat_request_digest(request),
        tenant_id="tenant-a",
        owner_id="owner-a",
    )
    turn = await route.chat_turn_lifecycle.advance(
        turn,
        TurnState.MODEL_RUNNING,
        tenant_id="tenant-a",
        owner_id="owner-a",
        reason_code="test-deferred-model-running",
    )
    assert turn.snapshot.state is TurnState.MODEL_RUNNING

    commit_calls = []

    async def get_thread(*_args, **_kwargs):
        return thread

    async def active_transcript(*_args, **_kwargs):
        return (user,)

    async def forbidden_commit(*args, **kwargs):
        commit_calls.append((args, kwargs))
        raise AssertionError(
            "deferred rejected response must not reach assistant commit"
        )

    async def append_message(message, **_kwargs):
        return thread, message

    monkeypatch.setattr(
        route,
        "conversation_authority",
        SimpleNamespace(
            get_thread=get_thread,
            active_transcript=active_transcript,
            commit_assistant_message=forbidden_commit,
            append_message=append_message,
        ),
    )

    user_segment = route.conversation_message_segment(
        thread,
        user,
        purpose="model-inference",
    )
    policy_segment = route.CHAT_INSTRUCTION_POLICY.to_segment(
        tenant_id="*",
        purpose="model-inference",
        created_at=user.created_at,
        mandatory=True,
    )
    binding = SimpleNamespace(
        operation_id=operation_id,
        execution_id=execution_id,
        turn_id=user.message_id,
        tenant_id="tenant-a",
        actor_id="owner-a",
        context_id="context-deferred-test",
        context_digest="c" * 64,
        compiler_version="test-v1",
        source_snapshot=(
            (user_segment.segment_id, user_segment.content_digest),
            (policy_segment.segment_id, policy_segment.content_digest),
        ),
        data_class=thread.data_class,
        purpose="model-inference",
        handoff_digest="d" * 64,
        capability="assistant.chat",
        idempotency_key=user.idempotency_key,
        trace_id="chat:" + operation_id,
    )
    engine_result = SimpleNamespace(
        operation_id=operation_id,
        execution_id=execution_id,
        final_output="Deferred output that must never be committed.",
        verification="unverified",
        evidence_refs=("evidence:deferred-rejected",),
        provider_receipts=("provider:test:deferred-rejected",),
        tool_receipts=(),
        memory_refs=(),
        artifact_refs=(),
    )
    fake_client = SimpleNamespace()

    async def status(*_args, **_kwargs):
        return {"execution_state": "completed"}

    async def terminal_result_if_available(**_kwargs):
        return engine_result

    async def handoff_binding(*_args, **_kwargs):
        return binding

    fake_client.status = status
    fake_client.terminal_result_if_available = terminal_result_if_available
    fake_client.handoff_binding = handoff_binding
    monkeypatch.setattr(route.EngineClient, "from_env", lambda: fake_client)

    response = await route.get_ai_chat_turn(
        thread.thread_id,
        idempotency_key=user.idempotency_key,
        user={"tenant_id": "tenant-a", "email": "owner-a"},
    )

    assert response["success"] is False
    assert response["state"] == "failed"
    assert response["failure_code"] == "response_acceptance_rejected"
    assert response["response_acceptance_receipt"].startswith(
        "response-acceptance-sha256:"
    )
    assert "verification_not_accepted" in (
        response["response_acceptance_reasons"]
    )
    assert commit_calls == []

    persisted = ai_chat_turn_test_authority.repo.reconstruct(
        operation_id,
        tenant_id="tenant-a",
        owner_id="owner-a",
    )
    assert persisted.snapshot.state is TurnState.FAILED_TERMINAL
    events = ai_chat_turn_test_authority.repo.list_events(
        operation_id,
        tenant_id="tenant-a",
        owner_id="owner-a",
    )
    assert events[-1].reason_code.startswith(
        "response-acceptance-rejected:"
    )
