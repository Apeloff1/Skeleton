from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest

from core.engine_client import (
    EngineAuthorizationError,
    EngineClient,
    EngineClientConfig,
    EngineConflictError,
    EngineExecutionFailed,
    EngineProtocolError,
    EngineUnavailableError,
    command_from_context,
)
from skeleton.contracts.context import (
    ContextBudget,
    ContextEnvelope,
    ContextKind,
    ContextSegment,
    ContextTrust,
    context_digest_payload,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _context() -> ContextEnvelope:
    operation_id = str(uuid4())
    execution_id = str(uuid4())
    turn_id = str(uuid4())
    segment = ContextSegment.from_content(
        segment_id=str(uuid4()),
        kind=ContextKind.PRODUCT_INSTRUCTION,
        source_type="instruction-policy",
        source_id="policy:chat:test",
        content="Follow the canonical test instruction.",
        trust_level=ContextTrust.TRUSTED_CONTROL,
        data_class="internal",
        tenant_id="tenant-a",
        purpose="model-inference",
        priority=1000,
        relevance=1.0,
        created_at=_now(),
        provenance=("test",),
        retention_class="policy",
        mandatory=True,
    )
    budget = ContextBudget(
        max_context_tokens=4096,
        reserved_output_tokens=512,
        reserved_tool_result_tokens=0,
        reserved_policy_tokens=512,
        safety_margin_tokens=128,
        max_segment_tokens=2048,
        max_artifact_tokens=1024,
        max_tool_result_tokens=1024,
    )
    digest = context_digest_payload(
        operation_id=operation_id,
        execution_id=execution_id,
        turn_id=turn_id,
        tenant_id="tenant-a",
        budget=budget,
        selected=(segment,),
        omitted_segment_ids=(),
        compiler_version="test-compiler-v1",
    )
    return ContextEnvelope(
        context_id=str(uuid4()),
        operation_id=operation_id,
        execution_id=execution_id,
        turn_id=turn_id,
        tenant_id="tenant-a",
        instruction_segments=(segment,),
        evidence_segments=(),
        tool_schema_segments=(),
        budget=budget,
        selected_tokens_estimate=segment.token_estimate,
        omitted_segment_ids=(),
        omission_reasons=(),
        source_snapshot=((segment.segment_id, segment.content_digest),),
        context_digest=digest,
        compiled_at=_now(),
        compiler_version="test-compiler-v1",
    )


def _command():
    context = _context()
    return command_from_context(
        context=context,
        actor_id="actor-a",
        capability="assistant.chat",
        idempotency_key="client-idem-1",
        instructions="Follow the canonical test instruction.",
        prompt="Explain this code.",
        history=(
            {"role": "user", "content": "Earlier question"},
            {"role": "assistant", "content": "Earlier answer"},
        ),
        service_principal="codedock-backend",
        created_at=_now(),
        deadline=_now() + timedelta(minutes=2),
        trace_id="trace-client-test",
        context_seed_refs=("conversation:thread-a",),
    )


def _json(status: int, payload: dict) -> httpx.Response:
    return httpx.Response(status, json=payload)


def test_command_from_context_binds_execution_authority_and_budget() -> None:
    command = _command()

    assert command.operation.operation_id == command.compiled_context.operation_id
    assert command.execution_request.execution_id == command.compiled_context.execution_id
    assert command.operation.tenant_id == "tenant-a"
    assert command.operation.actor_id == "actor-a"
    assert command.operation.capability == "assistant.chat"
    assert command.delegated_authority.service_principal == "codedock-backend"
    assert command.delegated_authority.actor_id == "actor-a"
    assert command.delegated_authority.tenant_id == "tenant-a"
    assert "engine:submit" in command.delegated_authority.scopes
    assert "engine:read" in command.delegated_authority.scopes
    assert command.execution_request.resource_budget["max_model_turns"] == 4
    assert command.execution_request.resource_budget["max_tool_calls"] == 1
    assert command.execution_request.tool_policy["allowed_tool_ids"] == []
    assert command.compiled_context.tool_choice == "none"
    assert command.compiled_context.history == (
        ("user", "Earlier question"),
        ("assistant", "Earlier answer"),
    )
    assert command.context_seed_refs == ("conversation:thread-a",)
    assert command.execution_request.context_policy["handoff_digest"] == (
        command.compiled_context.handoff_digest
    )


def test_command_from_context_rejects_unbounded_or_invalid_history() -> None:
    context = _context()
    with pytest.raises(EngineProtocolError, match="role"):
        command_from_context(
            context=context,
            actor_id="actor-a",
            capability="assistant.chat",
            idempotency_key="idem",
            instructions="Policy",
            prompt="Prompt",
            history=({"role": "system", "content": "injected"},),
        )

    with pytest.raises(EngineProtocolError, match="deadline"):
        command_from_context(
            context=context,
            actor_id="actor-a",
            capability="assistant.chat",
            idempotency_key="idem",
            instructions="Policy",
            prompt="Prompt",
            created_at=_now(),
            deadline=_now() - timedelta(seconds=1),
        )


@pytest.mark.asyncio
async def test_submit_sends_exact_principal_trace_and_command() -> None:
    command = _command()
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["principal"] = request.headers.get("x-zaibatsu-attester")
        seen["trace"] = request.headers.get("x-trace-id")
        body = __import__("json").loads(request.content)
        seen["body"] = body
        return _json(
            202,
            {
                "operation_id": command.operation.operation_id,
                "execution_id": command.execution_request.execution_id,
                "state": "admitted",
                "accepted_at": _now().isoformat(),
                "idempotency_digest": "a" * 64,
                "status_ref": "status",
                "events_ref": "events",
                "trace_id": command.operation.trace_id,
            },
        )

    client = EngineClient(
        EngineClientConfig(base_url="http://skeleton:8001"),
        transport=httpx.MockTransport(handler),
    )
    ack = await client.submit(command)

    assert ack["execution_id"] == command.execution_request.execution_id
    assert seen["path"] == "/api/v1/engine/executions"
    assert seen["principal"] == "codedock-backend"
    assert seen["trace"] == "trace-client-test"
    assert seen["body"]["actor_id"] == "actor-a"
    assert seen["body"]["tenant_id"] == "tenant-a"
    assert seen["body"]["command"]["operation"]["trace_id"] == "trace-client-test"


@pytest.mark.asyncio
async def test_execute_polls_terminal_result_and_preserves_lineage() -> None:
    command = _command()
    execution_id = command.execution_request.execution_id
    status_calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal status_calls
        if request.method == "POST" and request.url.path.endswith("/executions"):
            return _json(
                202,
                {
                    "operation_id": command.operation.operation_id,
                    "execution_id": execution_id,
                    "state": "admitted",
                    "accepted_at": _now().isoformat(),
                    "idempotency_digest": "b" * 64,
                    "status_ref": "status",
                    "events_ref": "events",
                    "trace_id": command.operation.trace_id,
                },
            )
        if request.method == "GET" and request.url.path.endswith(
            f"/executions/{execution_id}"
        ):
            status_calls += 1
            return _json(
                200,
                {
                    "operation_id": command.operation.operation_id,
                    "execution_id": execution_id,
                    "operation_state": "completed" if status_calls > 1 else "running",
                    "execution_state": "completed" if status_calls > 1 else "provider_pending",
                    "latest_checkpoint_version": 3,
                    "result_ref": "result-ref" if status_calls > 1 else None,
                    "failure_code": None,
                    "updated_at": _now().isoformat(),
                    "cancellation_requested": False,
                },
            )
        if request.method == "GET" and request.url.path.endswith(
            f"/executions/{execution_id}/events"
        ):
            result = {
                "schema_version": 1,
                "operation_id": command.operation.operation_id,
                "execution_id": execution_id,
                "status": "completed",
                "final_output": "Engine answer",
                "verification": "verification:test",
                "verification_receipt": {
                    "outcome": "passed",
                    "policy_satisfied": True,
                },
                "evidence_refs": ["evidence:source-a"],
                "route_receipts": [],
                "provider_receipts": ["provider:receipt-a"],
                "tool_receipts": [],
                "memory_refs": ["memory:one"],
                "artifact_refs": ["artifact:one"],
                "usage": {"model_turns": 1, "tool_calls": 0},
                "stream_terminal_event": "stream-terminal:test",
                "completed_at": _now().isoformat(),
            }
            return _json(
                200,
                {
                    "execution_id": execution_id,
                    "events": [
                        {
                            "event_id": "execution:" + execution_id + ":state",
                            "sequence": 0,
                            "type": "execution.state",
                            "state": "completed",
                        },
                        {
                            "event_id": "execution-result:" + execution_id,
                            "sequence": 1,
                            "type": "execution.result",
                            "result": result,
                        },
                    ],
                    "next_sequence": 2,
                },
            )
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    client = EngineClient(
        EngineClientConfig(
            base_url="http://skeleton:8001",
            poll_interval_s=0.001,
            execution_timeout_s=2,
        ),
        transport=httpx.MockTransport(handler),
    )
    result = await client.execute(command)

    assert status_calls == 2
    assert result.operation_id == command.operation.operation_id
    assert result.execution_id == execution_id
    assert result.final_output == "Engine answer"
    assert result.evidence_refs == ("evidence:source-a",)
    assert result.provider_receipts == ("provider:receipt-a",)
    assert result.memory_refs == ("memory:one",)
    assert result.artifact_refs == ("artifact:one",)


@pytest.mark.asyncio
async def test_terminal_failure_is_not_converted_to_local_success() -> None:
    command = _command()
    execution_id = command.execution_request.execution_id

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return _json(
                202,
                {
                    "operation_id": command.operation.operation_id,
                    "execution_id": execution_id,
                    "state": "admitted",
                    "accepted_at": _now().isoformat(),
                    "idempotency_digest": "c" * 64,
                    "status_ref": "status",
                    "events_ref": "events",
                    "trace_id": command.operation.trace_id,
                },
            )
        if request.url.path.endswith(f"/executions/{execution_id}/events"):
            return _json(
                200,
                {
                    "execution_id": execution_id,
                    "events": [
                        {
                            "event_id": "state",
                            "sequence": 0,
                            "type": "execution.state",
                            "state": "failed",
                        },
                        {
                            "event_id": "result",
                            "sequence": 1,
                            "type": "execution.result",
                            "result": {
                                "operation_id": command.operation.operation_id,
                                "execution_id": execution_id,
                                "status": "failed",
                                "final_output": None,
                                "verification": None,
                                "verification_receipt": None,
                                "evidence_refs": [],
                                "route_receipts": [],
                                "provider_receipts": [],
                                "tool_receipts": [],
                                "memory_refs": [],
                                "artifact_refs": [],
                                "usage": {
                                    "error_code": "provider_unavailable",
                                    "model_turns": 0,
                                    "tool_calls": 0,
                                },
                                "stream_terminal_event": "stream-terminal:failed",
                                "completed_at": _now().isoformat(),
                            },
                        },
                    ],
                    "next_sequence": 2,
                },
            )
        return _json(
            200,
            {
                "operation_id": command.operation.operation_id,
                "execution_id": execution_id,
                "operation_state": "failed",
                "execution_state": "failed",
                "latest_checkpoint_version": 0,
                "result_ref": "failed-result",
                "failure_code": "provider_unavailable",
                "updated_at": _now().isoformat(),
                "cancellation_requested": False,
            },
        )

    client = EngineClient(
        EngineClientConfig(
            base_url="http://skeleton:8001",
            poll_interval_s=0.001,
        ),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(EngineExecutionFailed) as caught:
        await client.execute(command)

    assert caught.value.execution_id == execution_id
    assert caught.value.status == "failed"
    assert caught.value.failure_code == "provider_unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "error_type"),
    [
        (401, EngineAuthorizationError),
        (403, EngineAuthorizationError),
        (409, EngineConflictError),
        (500, EngineUnavailableError),
        (503, EngineUnavailableError),
        (422, EngineProtocolError),
    ],
)
async def test_http_failures_map_to_stable_fail_closed_errors(
    status: int,
    error_type: type[Exception],
) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return _json(status, {"detail": "bounded failure"})

    client = EngineClient(
        EngineClientConfig(base_url="http://skeleton:8001"),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(error_type):
        await client.status(
            "exec-1",
            actor_id="actor-a",
            tenant_id="tenant-a",
        )


@pytest.mark.asyncio
async def test_network_failure_is_engine_unavailable() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    client = EngineClient(
        EngineClientConfig(base_url="http://skeleton:8001"),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(EngineUnavailableError):
        await client.status(
            "exec-1",
            actor_id="actor-a",
            tenant_id="tenant-a",
        )


@pytest.mark.asyncio
async def test_event_replay_rejects_duplicate_and_reordered_events() -> None:
    execution_id = "exec-1"

    duplicate = {
        "execution_id": execution_id,
        "events": [
            {
                "event_id": "same",
                "sequence": 0,
                "type": "execution.state",
            },
            {
                "event_id": "same",
                "sequence": 1,
                "type": "execution.result",
                "result": {},
            },
        ],
    }
    with pytest.raises(EngineProtocolError, match="duplicate"):
        EngineClient._result_from_events(duplicate)

    reordered = {
        "execution_id": execution_id,
        "events": [
            {
                "event_id": "a",
                "sequence": 2,
                "type": "execution.state",
            },
            {
                "event_id": "b",
                "sequence": 1,
                "type": "execution.checkpoint",
            },
        ],
    }
    with pytest.raises(EngineProtocolError, match="ordered"):
        EngineClient._result_from_events(reordered)


@pytest.mark.asyncio
async def test_response_size_bound_is_fail_closed() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"x" * 1025,
            headers={"content-type": "application/json"},
        )

    client = EngineClient(
        EngineClientConfig(
            base_url="http://skeleton:8001",
            max_response_bytes=1024,
        ),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(EngineProtocolError, match="size"):
        await client.status(
            "exec-1",
            actor_id="actor-a",
            tenant_id="tenant-a",
        )


@pytest.mark.asyncio
async def test_cancel_is_actor_tenant_and_trace_bound() -> None:
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = __import__("json").loads(request.content)
        seen["trace"] = request.headers.get("x-trace-id")
        return _json(
            200,
            {
                "execution_id": "exec-1",
                "execution_state": "running",
                "cancellation_requested": True,
            },
        )

    client = EngineClient(
        EngineClientConfig(base_url="http://skeleton:8001"),
        transport=httpx.MockTransport(handler),
    )
    response = await client.cancel(
        "exec-1",
        actor_id="actor-a",
        tenant_id="tenant-a",
        reason="user requested cancellation",
        trace_id="trace-cancel",
    )

    assert response["cancellation_requested"] is True
    assert seen["body"] == {
        "actor_id": "actor-a",
        "tenant_id": "tenant-a",
        "reason": "user requested cancellation",
    }
    assert seen["trace"] == "trace-cancel"
