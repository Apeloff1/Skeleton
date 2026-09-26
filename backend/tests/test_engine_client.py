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
from skeleton.provider_contract import ProviderToolDefinition
from skeleton.context.compiler import ContextCompiler
from skeleton.contracts.context import (
    ContextBudget,
    ContextEnvelope,
    ContextKind,
    ContextSegment,
    ContextTrust,
    context_digest_payload,
)


_SERVICE_TOKEN = "test-engine-service-token-" + ("x" * 32)


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


def _projected_context() -> ContextEnvelope:
    operation_id = str(uuid4())
    execution_id = str(uuid4())
    turn_id = str(uuid4())
    created_at = _now()
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
    segments = (
        ContextSegment.from_content(
            segment_id=str(uuid4()),
            kind=ContextKind.PRODUCT_INSTRUCTION,
            source_type="product-policy",
            source_id="policy:projected",
            content="Canonical projected instruction.",
            trust_level=ContextTrust.TRUSTED_CONTROL,
            data_class="internal",
            tenant_id="tenant-a",
            purpose="model-inference",
            priority=1000,
            relevance=1.0,
            created_at=created_at,
            provenance=("test",),
            retention_class="policy",
            mandatory=True,
        ),
        ContextSegment.from_content(
            segment_id=str(uuid4()),
            kind=ContextKind.USER_MESSAGE,
            source_type="conversation",
            source_id="message:earlier-user",
            content="Canonical earlier question.",
            trust_level=ContextTrust.AUTHORIZED_USER_DATA,
            data_class="internal",
            tenant_id="tenant-a",
            purpose="model-inference",
            priority=700,
            relevance=1.0,
            created_at=created_at,
            provenance=("test",),
            retention_class="conversation",
        ),
        ContextSegment.from_content(
            segment_id=str(uuid4()),
            kind=ContextKind.ASSISTANT_MESSAGE,
            source_type="conversation",
            source_id="message:earlier-assistant",
            content="Canonical earlier answer.",
            trust_level=ContextTrust.DERIVED_UNTRUSTED,
            data_class="internal",
            tenant_id="tenant-a",
            purpose="model-inference",
            priority=700,
            relevance=1.0,
            created_at=created_at + timedelta(milliseconds=1),
            provenance=("test",),
            retention_class="conversation",
        ),
        ContextSegment.from_content(
            segment_id=str(uuid4()),
            kind=ContextKind.USER_MESSAGE,
            source_type="conversation",
            source_id="message:current-user",
            content="Canonical current question.",
            trust_level=ContextTrust.AUTHORIZED_USER_DATA,
            data_class="internal",
            tenant_id="tenant-a",
            purpose="model-inference",
            priority=900,
            relevance=1.0,
            created_at=created_at + timedelta(milliseconds=2),
            provenance=("test",),
            retention_class="conversation",
        ),
    )
    return ContextCompiler().compile(
        operation_id=operation_id,
        execution_id=execution_id,
        turn_id=turn_id,
        tenant_id="tenant-a",
        purpose="model-inference",
        budget=budget,
        segments=segments,
        tools_enabled=False,
        compiled_at=created_at,
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
    assert "engine:approve" not in command.delegated_authority.scopes
    assert command.execution_request.resource_budget["max_model_turns"] == 4
    assert command.execution_request.resource_budget["max_tool_calls"] == 1
    resource_budget = command.execution_request.resource_budget
    assert resource_budget["max_input_tokens"] == 4096 - 512 - 128
    assert 0 < resource_budget["selected_input_tokens_estimate"] <= (
        resource_budget["max_input_tokens"]
    )
    assert resource_budget["max_output_tokens"] == 512
    assert resource_budget["max_tool_result_tokens"] == 0
    assert command.execution_request.tool_policy["allowed_tool_ids"] == []
    assert command.execution_request.context_policy["verification_profile"] == "evidence_required"
    assert command.compiled_context.tool_choice == "none"
    assert command.compiled_context.history == (
        ("user", "Earlier question"),
        ("assistant", "Earlier answer"),
    )
    assert command.context_seed_refs == ("conversation:thread-a",)
    assert command.execution_request.context_policy["handoff_digest"] == (
        command.compiled_context.handoff_digest
    )


def test_command_from_context_uses_context_projection_over_legacy_text() -> None:
    context = _projected_context()

    command = command_from_context(
        context=context,
        actor_id="actor-a",
        capability="assistant.chat",
        idempotency_key="projection-authority",
        instructions="ATTACKER OVERRIDE",
        prompt="ATTACKER PROMPT",
        history=(
            {"role": "user", "content": "ATTACKER HISTORY"},
        ),
    )

    assert command.compiled_context.instructions == (
        "Canonical projected instruction."
    )
    assert command.compiled_context.prompt == "Canonical current question."
    assert command.compiled_context.history == (
        ("user", "Canonical earlier question."),
        ("assistant", "Canonical earlier answer."),
    )
    assert "ATTACKER" not in command.compiled_context.instructions
    assert "ATTACKER" not in command.compiled_context.prompt
    assert all(
        "ATTACKER" not in content
        for _role, content in command.compiled_context.history
    )


def test_command_from_context_binds_assistant_proposal_profile() -> None:
    context = _context()
    command = command_from_context(
        context=context,
        actor_id="actor-a",
        capability="assistant.chat",
        idempotency_key="proposal-idem",
        instructions="Policy",
        prompt="Prompt",
        verification_profile="assistant_proposal",
    )

    assert command.execution_request.context_policy["verification_profile"] == "assistant_proposal"
    assert command.execution_request.tool_policy["allowed_tool_ids"] == []


def test_command_from_context_rejects_assistant_profile_for_non_assistant_capability() -> None:
    context = _context()
    with pytest.raises(EngineProtocolError, match="assistant capability"):
        command_from_context(
            context=context,
            actor_id="actor-a",
            capability="admin.execute",
            idempotency_key="proposal-idem",
            instructions="Policy",
            prompt="Prompt",
            verification_profile="assistant_proposal",
        )


def test_rebuilt_command_keeps_submission_digest_across_fresh_authority() -> None:
    context = _context()
    started = _now()
    first = command_from_context(
        context=context,
        actor_id="actor-a",
        capability="assistant.chat",
        idempotency_key="retry-idem",
        instructions="Policy",
        prompt="Prompt",
        verification_profile="assistant_proposal",
        created_at=started,
        deadline=started + timedelta(minutes=2),
    )
    retry_started = started + timedelta(seconds=30)
    retry = command_from_context(
        context=context,
        actor_id="actor-a",
        capability="assistant.chat",
        idempotency_key="retry-idem",
        instructions="Policy",
        prompt="Prompt",
        verification_profile="assistant_proposal",
        created_at=retry_started,
        deadline=retry_started + timedelta(minutes=2),
    )

    assert first.command_digest != retry.command_digest
    assert first.submission_digest == retry.submission_digest
    assert first.execution_request.identity_digest == retry.execution_request.identity_digest
    assert first.operation.identity_digest == retry.operation.identity_digest


def test_command_from_context_binds_tool_definitions_and_choice() -> None:
    context = _context()
    tool = ProviderToolDefinition(
        tool_id="repo.read",
        description="Read one repository file.",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    )
    command = command_from_context(
        context=context,
        actor_id="actor-a",
        capability="assistant.chat",
        idempotency_key="tool-idem",
        instructions="Use the allowed tool when required.",
        prompt="Read README.md.",
        tools=(tool,),
        tool_choice="required",
        max_tool_calls=2,
    )

    assert command.compiled_context.tools == (tool,)
    assert command.compiled_context.tool_choice == "required"
    assert command.execution_request.tool_policy["allowed_tool_ids"] == [
        "repo.read"
    ]
    assert command.execution_request.context_policy["tool_choice"] == "required"
    assert command.execution_request.context_policy["specific_tool_id"] is None
    assert "engine:approve" in command.delegated_authority.scopes


def test_command_from_context_rejects_tools_for_assistant_proposal() -> None:
    context = _context()
    tool = ProviderToolDefinition(
        tool_id="repo.read",
        description="Read one repository file.",
        input_schema={"type": "object"},
    )
    with pytest.raises(
        EngineProtocolError,
        match="tool-free execution",
    ):
        command_from_context(
            context=context,
            actor_id="actor-a",
            capability="assistant.chat",
            idempotency_key="proposal-tool-idem",
            instructions="Policy",
            prompt="Prompt",
            verification_profile="assistant_proposal",
            tools=(tool,),
        )


def test_command_from_context_rejects_specific_tool_not_offered() -> None:
    context = _context()
    tool = ProviderToolDefinition(
        tool_id="repo.read",
        description="Read one repository file.",
        input_schema={"type": "object"},
    )
    with pytest.raises(
        EngineProtocolError,
        match="not offered",
    ):
        command_from_context(
            context=context,
            actor_id="actor-a",
            capability="assistant.chat",
            idempotency_key="specific-tool-idem",
            instructions="Policy",
            prompt="Prompt",
            tools=(tool,),
            tool_choice="specific",
            specific_tool_id="repo.write",
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
        seen["authorization"] = request.headers.get("authorization")
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
        EngineClientConfig(service_token=_SERVICE_TOKEN, base_url="http://skeleton:8001"),
        transport=httpx.MockTransport(handler),
    )
    ack = await client.submit(command)

    assert ack["execution_id"] == command.execution_request.execution_id
    assert seen["path"] == "/api/v1/engine/executions"
    assert seen["principal"] == "codedock-backend"
    assert seen["authorization"] == "Bearer " + _SERVICE_TOKEN
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
            service_token=_SERVICE_TOKEN,
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
async def test_execute_recovers_ambiguous_submit_by_query_without_resubmit() -> None:
    command = _command()
    execution_id = command.execution_request.execution_id
    post_calls = 0
    status_calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_calls, status_calls
        if request.method == "POST" and request.url.path.endswith("/executions"):
            post_calls += 1
            raise httpx.ReadTimeout("submit response lost", request=request)
        if request.method == "GET" and request.url.path.endswith(
            f"/executions/{execution_id}"
        ):
            status_calls += 1
            state = "provider_pending" if status_calls == 1 else "completed"
            return _json(
                200,
                {
                    "operation_id": command.operation.operation_id,
                    "execution_id": execution_id,
                    "operation_state": "running" if state != "completed" else "completed",
                    "execution_state": state,
                    "latest_checkpoint_version": 1,
                    "result_ref": None if state != "completed" else "execution-result:" + execution_id,
                    "failure_code": None,
                    "updated_at": _now().isoformat(),
                    "cancellation_requested": False,
                },
            )
        if request.method == "GET" and request.url.path.endswith(
            f"/executions/{execution_id}/events"
        ):
            return _json(
                200,
                {
                    "execution_id": execution_id,
                    "events": [
                        {
                            "event_id": "state",
                            "sequence": 0,
                            "type": "execution.state",
                            "state": "completed",
                        },
                        {
                            "event_id": "result",
                            "sequence": 1,
                            "type": "execution.result",
                            "result": {
                                "schema_version": 1,
                                "operation_id": command.operation.operation_id,
                                "execution_id": execution_id,
                                "status": "completed",
                                "final_output": "recovered answer",
                                "verification": "verification:recovered",
                                "verification_receipt": {
                                    "outcome": "passed",
                                    "policy_satisfied": True,
                                },
                                "evidence_refs": ["evidence:recovered"],
                                "route_receipts": [],
                                "provider_receipts": ["provider:recovered"],
                                "tool_receipts": [],
                                "memory_refs": [],
                                "artifact_refs": [],
                                "usage": {"model_turns": 1, "tool_calls": 0},
                                "stream_terminal_event": "stream-terminal:recovered",
                                "completed_at": _now().isoformat(),
                            },
                        },
                    ],
                    "next_sequence": 2,
                },
            )
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    client = EngineClient(
        EngineClientConfig(
            base_url="http://skeleton:8001",
            service_token=_SERVICE_TOKEN,
            poll_interval_s=0.001,
            execution_timeout_s=2,
        ),
        transport=httpx.MockTransport(handler),
    )
    result = await client.execute(command)

    assert result.final_output == "recovered answer"
    assert post_calls == 1
    assert status_calls == 2


@pytest.mark.asyncio
async def test_execute_queries_before_single_resubmit_when_first_submit_not_found() -> None:
    command = _command()
    execution_id = command.execution_request.execution_id
    calls: list[str] = []
    post_calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_calls
        calls.append(request.method + " " + request.url.path)
        if request.method == "POST" and request.url.path.endswith("/executions"):
            post_calls += 1
            if post_calls == 1:
                raise httpx.ReadTimeout("submit response lost", request=request)
            return _json(
                202,
                {
                    "operation_id": command.operation.operation_id,
                    "execution_id": execution_id,
                    "state": "admitted",
                    "accepted_at": _now().isoformat(),
                    "idempotency_digest": "d" * 64,
                    "status_ref": "status",
                    "events_ref": "events",
                    "trace_id": command.operation.trace_id,
                },
            )
        if request.method == "GET" and request.url.path.endswith(
            f"/executions/{execution_id}"
        ):
            if post_calls == 1:
                return _json(404, {"detail": "unknown engine execution"})
            return _json(
                200,
                {
                    "operation_id": command.operation.operation_id,
                    "execution_id": execution_id,
                    "operation_state": "completed",
                    "execution_state": "completed",
                    "latest_checkpoint_version": 1,
                    "result_ref": "execution-result:" + execution_id,
                    "failure_code": None,
                    "updated_at": _now().isoformat(),
                    "cancellation_requested": False,
                },
            )
        if request.method == "GET" and request.url.path.endswith(
            f"/executions/{execution_id}/events"
        ):
            return _json(
                200,
                {
                    "execution_id": execution_id,
                    "events": [
                        {
                            "event_id": "result",
                            "sequence": 0,
                            "type": "execution.result",
                            "result": {
                                "schema_version": 1,
                                "operation_id": command.operation.operation_id,
                                "execution_id": execution_id,
                                "status": "completed",
                                "final_output": "retried answer",
                                "verification": "verification:retry",
                                "verification_receipt": {
                                    "outcome": "passed",
                                    "policy_satisfied": True,
                                },
                                "evidence_refs": ["evidence:retry"],
                                "route_receipts": [],
                                "provider_receipts": ["provider:retry"],
                                "tool_receipts": [],
                                "memory_refs": [],
                                "artifact_refs": [],
                                "usage": {"model_turns": 1, "tool_calls": 0},
                                "stream_terminal_event": "stream-terminal:retry",
                                "completed_at": _now().isoformat(),
                            },
                        }
                    ],
                    "next_sequence": 1,
                },
            )
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    client = EngineClient(
        EngineClientConfig(
            base_url="http://skeleton:8001",
            service_token=_SERVICE_TOKEN,
            poll_interval_s=0.001,
            execution_timeout_s=2,
        ),
        transport=httpx.MockTransport(handler),
    )
    result = await client.execute(command)

    assert result.final_output == "retried answer"
    assert post_calls == 2
    assert calls[:3] == [
        "POST /api/v1/engine/executions",
        f"GET /api/v1/engine/executions/{execution_id}",
        "POST /api/v1/engine/executions",
    ]


@pytest.mark.asyncio
async def test_execute_rejects_mismatched_recovered_submit_identity() -> None:
    command = _command()
    execution_id = command.execution_request.execution_id
    post_calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_calls
        if request.method == "POST":
            post_calls += 1
            raise httpx.ReadTimeout("submit response lost", request=request)
        if request.method == "GET" and request.url.path.endswith(
            f"/executions/{execution_id}"
        ):
            return _json(
                200,
                {
                    "operation_id": str(uuid4()),
                    "execution_id": execution_id,
                    "operation_state": "running",
                    "execution_state": "provider_pending",
                    "latest_checkpoint_version": 0,
                    "result_ref": None,
                    "failure_code": None,
                    "updated_at": _now().isoformat(),
                    "cancellation_requested": False,
                },
            )
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    client = EngineClient(
        EngineClientConfig(
            base_url="http://skeleton:8001",
            service_token=_SERVICE_TOKEN,
        ),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(
        EngineProtocolError,
        match="recovered engine status operation identity mismatch",
    ):
        await client.execute(command)
    assert post_calls == 1


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
            service_token=_SERVICE_TOKEN,
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
        EngineClientConfig(service_token=_SERVICE_TOKEN, base_url="http://skeleton:8001"),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(error_type):
        await client.status(
            "exec-1",
            actor_id="actor-a",
            tenant_id="tenant-a",
        )


@pytest.mark.asyncio
async def test_pending_approval_query_validates_bound_identity() -> None:
    execution_id = "exec-approval"
    digest = "a" * 64

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == (
            "/api/v1/engine/executions/"
            + execution_id
            + "/tool-approvals/pending"
        )
        assert request.url.params["actor_id"] == "actor-a"
        assert request.url.params["tenant_id"] == "tenant-a"
        return _json(
            200,
            {
                "execution_id": execution_id,
                "pending": [
                    {
                        "call_id": "call-1",
                        "tool_id": "repo.write",
                        "arguments_digest": digest,
                        "idempotency_key": "approval-idem",
                        "approval_ref": "approval:bound-ref",
                    }
                ],
            },
        )

    client = EngineClient(
        EngineClientConfig(
            base_url="http://skeleton:8001",
            service_token=_SERVICE_TOKEN,
        ),
        transport=httpx.MockTransport(handler),
    )
    pending = await client.pending_tool_approvals(
        execution_id,
        actor_id="actor-a",
        tenant_id="tenant-a",
    )

    assert pending == (
        {
            "call_id": "call-1",
            "tool_id": "repo.write",
            "arguments_digest": digest,
            "idempotency_key": "approval-idem",
            "approval_ref": "approval:bound-ref",
        },
    )


@pytest.mark.asyncio
async def test_approve_tool_call_posts_exact_pending_identity() -> None:
    execution_id = "exec-approval"
    digest = "b" * 64
    expiry = _now() + timedelta(minutes=1)
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = __import__("json").loads(request.content)
        return _json(
            202,
            {
                "schema_version": 1,
                "approval_id": "approval-id",
                "approval_ref": "approval:bound-ref",
                "execution_id": execution_id,
                "call_id": "call-1",
                "tool_id": "repo.write",
                "arguments_digest": digest,
                "actor_id": "actor-a",
                "tenant_id": "tenant-a",
                "idempotency_key": "approval-idem",
                "issued_at": _now().isoformat(),
                "expires_at": expiry.isoformat(),
            },
        )

    client = EngineClient(
        EngineClientConfig(
            base_url="http://skeleton:8001",
            service_token=_SERVICE_TOKEN,
        ),
        transport=httpx.MockTransport(handler),
    )
    approval = await client.approve_tool_call(
        execution_id,
        actor_id="actor-a",
        tenant_id="tenant-a",
        call_id="call-1",
        tool_id="repo.write",
        arguments_digest=digest,
        idempotency_key="approval-idem",
        expires_at=expiry,
    )

    assert seen["path"] == (
        "/api/v1/engine/executions/"
        + execution_id
        + "/tool-approvals"
    )
    assert seen["body"]["arguments_digest"] == digest
    assert seen["body"]["idempotency_key"] == "approval-idem"
    assert approval["approval_ref"] == "approval:bound-ref"


@pytest.mark.asyncio
async def test_pending_approval_rejects_malformed_server_identity() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return _json(
            200,
            {
                "execution_id": "exec-approval",
                "pending": [
                    {
                        "call_id": "call-1",
                        "tool_id": "repo.write",
                        "arguments_digest": "bad",
                        "idempotency_key": "approval-idem",
                        "approval_ref": "approval:bound-ref",
                    }
                ],
            },
        )

    client = EngineClient(
        EngineClientConfig(
            base_url="http://skeleton:8001",
            service_token=_SERVICE_TOKEN,
        ),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(EngineProtocolError, match="arguments_digest"):
        await client.pending_tool_approvals(
            "exec-approval",
            actor_id="actor-a",
            tenant_id="tenant-a",
        )


@pytest.mark.asyncio
async def test_network_failure_is_engine_unavailable() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    client = EngineClient(
        EngineClientConfig(service_token=_SERVICE_TOKEN, base_url="http://skeleton:8001"),
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
            service_token=_SERVICE_TOKEN,
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
        EngineClientConfig(service_token=_SERVICE_TOKEN, base_url="http://skeleton:8001"),
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



def test_engine_client_config_masks_service_token_in_repr() -> None:
    config = EngineClientConfig(
        base_url="http://skeleton:8001",
        service_token=_SERVICE_TOKEN,
    )

    assert _SERVICE_TOKEN not in repr(config)


def test_engine_env_requires_service_token_when_url_configured(monkeypatch) -> None:
    monkeypatch.setenv("SKELETON_INTERNAL_URL", "http://skeleton:8001")
    monkeypatch.delenv("SKL_ENGINE_SERVICE_TOKEN", raising=False)

    with pytest.raises(EngineProtocolError, match="service token"):
        EngineClientConfig.from_env()

    monkeypatch.setenv("SKL_ENGINE_SERVICE_TOKEN", _SERVICE_TOKEN)
    config = EngineClientConfig.from_env()

    assert config is not None
    assert config.service_token == _SERVICE_TOKEN


@pytest.mark.asyncio
async def test_client_rejects_missing_service_token_before_transport() -> None:
    called = False

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return _json(200, {})

    client = EngineClient(
        EngineClientConfig(base_url="http://skeleton:8001"),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(EngineAuthorizationError, match="service token"):
        await client.status(
            "exec-1",
            actor_id="actor-a",
            tenant_id="tenant-a",
        )

    assert called is False

def test_command_from_context_rejects_output_above_compiled_reserve() -> None:
    context = _context()

    with pytest.raises(
        EngineProtocolError,
        match="max_output_tokens exceeds compiled context reserve",
    ):
        command_from_context(
            context=context,
            actor_id="actor-a",
            capability="assistant.chat",
            idempotency_key="output-over-reserve",
            instructions="Policy",
            prompt="Prompt",
            max_output_tokens=context.budget.reserved_output_tokens + 1,
        )


def test_command_from_context_allows_smaller_explicit_output_budget() -> None:
    context = _context()
    command = command_from_context(
        context=context,
        actor_id="actor-a",
        capability="assistant.chat",
        idempotency_key="output-under-reserve",
        instructions="Policy",
        prompt="Prompt",
        max_output_tokens=128,
    )

    assert command.execution_request.resource_budget["max_output_tokens"] == 128
    assert command.execution_request.resource_budget["max_input_tokens"] == (
        context.budget.input_capacity(tools_enabled=False)
    )
    assert command.execution_request.resource_budget[
        "selected_input_tokens_estimate"
    ] == context.selected_tokens_estimate

def test_command_from_context_requires_positive_compiled_output_reserve() -> None:
    context = _context()
    zero_budget = ContextBudget(
        max_context_tokens=context.budget.max_context_tokens,
        reserved_output_tokens=0,
        reserved_tool_result_tokens=0,
        reserved_policy_tokens=context.budget.reserved_policy_tokens,
        safety_margin_tokens=context.budget.safety_margin_tokens,
        max_segment_tokens=context.budget.max_segment_tokens,
        max_artifact_tokens=context.budget.max_artifact_tokens,
        max_tool_result_tokens=context.budget.max_tool_result_tokens,
    )
    rebound = ContextEnvelope(
        context_id=context.context_id,
        operation_id=context.operation_id,
        execution_id=context.execution_id,
        turn_id=context.turn_id,
        tenant_id=context.tenant_id,
        instruction_segments=context.instruction_segments,
        evidence_segments=context.evidence_segments,
        tool_schema_segments=context.tool_schema_segments,
        budget=zero_budget,
        selected_tokens_estimate=context.selected_tokens_estimate,
        omitted_segment_ids=context.omitted_segment_ids,
        omission_reasons=context.omission_reasons,
        source_snapshot=context.source_snapshot,
        context_digest=context_digest_payload(
            operation_id=context.operation_id,
            execution_id=context.execution_id,
            turn_id=context.turn_id,
            tenant_id=context.tenant_id,
            budget=zero_budget,
            selected=context.selected_segments,
            omitted_segment_ids=context.omitted_segment_ids,
            compiler_version=context.compiler_version,
        ),
        compiled_at=context.compiled_at,
        compiler_version=context.compiler_version,
    )

    with pytest.raises(
        EngineProtocolError,
        match="positive output reserve",
    ):
        command_from_context(
            context=rebound,
            actor_id="actor-a",
            capability="assistant.chat",
            idempotency_key="zero-output-reserve",
            instructions="Policy",
            prompt="Prompt",
        )

@pytest.mark.asyncio
async def test_storage_admission_client_uses_engine_boundary_and_bounded_body() -> None:
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["principal"] = request.headers.get("x-zaibatsu-attester")
        seen["authorization"] = request.headers.get("authorization")
        seen["trace"] = request.headers.get("x-trace-id")
        seen["body"] = __import__("json").loads(request.content)
        return _json(
            200,
            {
                "schema_version": 1,
                "receipt_id": "storage-admission:test",
                "operation_id": str(uuid4()),
                "tenant_id": "tenant-a",
                "capability": "conversation-persistence",
                "resource_id": "conversation-message",
                "write_id": "thread-a:idem-1",
                "storage_bytes": 321,
                "admitted_at": _now().isoformat(),
                "quota_reservation_id": "qrs-test",
                "admission_decision_id": "adm-test",
                "replayed": False,
            },
        )

    client = EngineClient(
        EngineClientConfig(
            service_token=_SERVICE_TOKEN,
            base_url="http://skeleton:8001",
        ),
        transport=httpx.MockTransport(handler),
    )
    receipt = await client.admit_storage_write(
        tenant_id="tenant-a",
        capability="conversation-persistence",
        resource_id="conversation-message",
        write_id="thread-a:idem-1",
        storage_bytes=321,
        trace_id="trace-storage",
    )

    assert receipt["storage_bytes"] == 321
    assert seen["path"] == "/api/v1/engine/admission/storage"
    assert seen["principal"] == "codedock-backend"
    assert seen["authorization"] == "Bearer " + _SERVICE_TOKEN
    assert seen["trace"] == "trace-storage"
    assert seen["body"] == {
        "tenant_id": "tenant-a",
        "capability": "conversation-persistence",
        "resource_id": "conversation-message",
        "write_id": "thread-a:idem-1",
        "storage_bytes": 321,
    }


@pytest.mark.asyncio
async def test_storage_admission_client_rejects_invalid_size_before_io() -> None:
    called = False

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return _json(500, {"detail": "must not be reached"})

    client = EngineClient(
        EngineClientConfig(
            service_token=_SERVICE_TOKEN,
            base_url="http://skeleton:8001",
        ),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(EngineProtocolError, match="storage_bytes"):
        await client.admit_storage_write(
            tenant_id="tenant-a",
            capability="conversation-persistence",
            resource_id="conversation-message",
            write_id="thread-a:idem-1",
            storage_bytes=0,
        )

    assert called is False

@pytest.mark.asyncio
async def test_governance_write_client_posts_bounded_metadata() -> None:
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["principal"] = request.headers.get("x-zaibatsu-attester")
        seen["authorization"] = request.headers.get("authorization")
        seen["body"] = __import__("json").loads(request.content)
        return _json(
            200,
            {
                "schema_version": 1,
                "mode": "register",
                "record": {
                    "record_id": "message-1",
                    "tenant_id": "tenant-a",
                    "owner_plane": "conversation",
                    "source_ref": "conversation-message://thread-1/message-1",
                    "data_class": "internal",
                    "purposes": ["model-inference"],
                    "deletion_targets": ["conversation"],
                    "created_at": 100.0,
                    "retention_until": None,
                    "exportable": True,
                    "state": "active",
                },
            },
        )

    client = EngineClient(
        EngineClientConfig(
            service_token=_SERVICE_TOKEN,
            base_url="http://skeleton:8001",
        ),
        transport=httpx.MockTransport(handler),
    )
    receipt = await client.reconcile_governed_write(
        mode="register",
        plane="conversation",
        record_id="message-1",
        tenant_id="tenant-a",
        source_ref="conversation-message://thread-1/message-1",
        data_class="internal",
        purposes=("model-inference",),
        deletion_targets=("conversation",),
        created_at=100.0,
    )

    assert receipt["record"]["owner_plane"] == "conversation"
    assert seen["path"] == "/api/v1/engine/governance/writes"
    assert seen["principal"] == "codedock-backend"
    assert seen["authorization"] == "Bearer " + _SERVICE_TOKEN
    assert seen["body"] == {
        "mode": "register",
        "plane": "conversation",
        "record_id": "message-1",
        "tenant_id": "tenant-a",
        "source_ref": "conversation-message://thread-1/message-1",
        "data_class": "internal",
        "purposes": ["model-inference"],
        "deletion_targets": ["conversation"],
        "created_at": 100.0,
        "retention_until": None,
        "exportable": True,
    }


@pytest.mark.asyncio
async def test_governance_write_client_rejects_malformed_lists_before_io() -> None:
    called = False

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return _json(500, {"detail": "must not be reached"})

    client = EngineClient(
        EngineClientConfig(
            service_token=_SERVICE_TOKEN,
            base_url="http://skeleton:8001",
        ),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(EngineProtocolError, match="purposes"):
        await client.reconcile_governed_write(
            mode="register",
            plane="conversation",
            record_id="message-1",
            tenant_id="tenant-a",
            source_ref="conversation-message://thread-1/message-1",
            data_class="internal",
            purposes=(),
        )

    assert called is False


def test_command_from_context_binds_explicit_verified_memory_intent() -> None:
    context = _context()

    command = command_from_context(
        context=context,
        actor_id="actor-a",
        capability="assistant.chat",
        idempotency_key="memory-intent",
        instructions="ignored legacy instruction",
        prompt="remember this verified outcome",
        verification_profile="assistant_proposal",
        memory_write_intent={
            "subject_id": "user-a",
            "namespace": "assistant",
            "kind": "semantic",
            "content_from": "verified_final_output",
            "data_class": "confidential",
            "provenance_refs": ["conversation:thread-a"],
        },
    )

    intent = command.execution_request.context_policy[
        "memory_write_intent"
    ]
    assert intent == {
        "subject_id": "user-a",
        "namespace": "assistant",
        "kind": "semantic",
        "data_class": "confidential",
        "content_from": "verified_final_output",
        "provenance_refs": ["conversation:thread-a"],
    }
    assert "engine:memory" in command.delegated_authority.scopes


def test_command_from_context_rejects_unverified_memory_content_source() -> None:
    context = _context()

    with pytest.raises(
        EngineProtocolError,
        match="only persist verified_final_output",
    ):
        command_from_context(
            context=context,
            actor_id="actor-a",
            capability="assistant.chat",
            idempotency_key="memory-intent-invalid",
            instructions="canonical",
            prompt="hello",
            verification_profile="assistant_proposal",
            memory_write_intent={
                "subject_id": "user-a",
                "kind": "semantic",
                "content_from": "raw_model_output",
            },
        )


def test_command_without_memory_intent_does_not_delegate_memory_scope() -> None:
    context = _context()

    command = command_from_context(
        context=context,
        actor_id="actor-a",
        capability="assistant.chat",
        idempotency_key="no-memory-intent",
        instructions="canonical",
        prompt="hello",
        verification_profile="assistant_proposal",
    )

    assert "memory_write_intent" not in (
        command.execution_request.context_policy
    )
    assert "engine:memory" not in command.delegated_authority.scopes
