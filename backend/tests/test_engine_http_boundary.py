from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from core.engine_client import (
    EngineAuthorizationError,
    EngineClient,
    EngineExecutionFailed,
    EngineClientConfig,
    command_from_context,
)
from skeleton.api.engine_authority import (
    EngineAuthorityRegistry,
    EngineServiceGrant,
)
from skeleton.api.engine_routes import (
    _engine_coordinator,
    _engine_service,
    _engine_service_token,
    router,
)
from skeleton.api.engine_service import (
    EngineExecutionService,
    SQLiteEngineSubmissionStore,
)
from skeleton.api.engine_runtime import EngineExecutionCoordinator
from skeleton.intelligence.execution_runtime import ExecutionVerificationDecision
from skeleton.contracts.context import (
    ContextBudget,
    ContextEnvelope,
    ContextKind,
    ContextSegment,
    ContextTrust,
    context_digest_payload,
)
from skeleton.persistence.execution_repository import SQLiteExecutionRepository
from skeleton.provider_contract import (
    FinishReason,
    ProviderToolCall,
    ProviderToolDefinition,
    ProviderUsage,
)
from skeleton.provider_runtime import ProviderResponse
from skeleton.skills.tool_contract import ToolEffect, ToolManifest
from skeleton.skills.tool_runtime import AsyncToolRuntime


_SERVICE_TOKEN = "cross-service-engine-token-" + ("x" * 40)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _context() -> ContextEnvelope:
    operation_id = str(uuid4())
    execution_id = str(uuid4())
    turn_id = str(uuid4())
    segment = ContextSegment.from_content(
        segment_id=str(uuid4()),
        kind=ContextKind.PRODUCT_INSTRUCTION,
        source_type="cross-service-policy",
        source_id="policy:cross-service-test",
        content="Follow the cross-service test policy.",
        trust_level=ContextTrust.TRUSTED_CONTROL,
        data_class="internal",
        tenant_id="tenant-a",
        purpose="model-inference",
        priority=1000,
        relevance=1.0,
        created_at=_now(),
        provenance=("cross-service-test",),
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
        compiler_version="cross-service-v1",
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
        compiler_version="cross-service-v1",
    )


def _service(tmp_path) -> EngineExecutionService:
    authorities = EngineAuthorityRegistry(
        [
            EngineServiceGrant(
                service_principal="codedock-backend",
                scopes=frozenset(
                    {
                        "engine:submit",
                        "engine:read",
                        "engine:cancel",
                        "engine:events",
                        "engine:approve",
                    }
                ),
                tenant_ids=frozenset({"tenant-a"}),
                capabilities=frozenset({"assistant.chat"}),
            )
        ]
    )
    return EngineExecutionService(
        SQLiteExecutionRepository(tmp_path / "http-boundary-execution.sqlite3"),
        SQLiteEngineSubmissionStore(tmp_path / "http-boundary-submission.sqlite3"),
        authorities,
    )


def _app(
    service: EngineExecutionService,
    *,
    coordinator=None,
) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[_engine_service] = lambda: service
    app.dependency_overrides[_engine_service_token] = lambda: _SERVICE_TOKEN
    app.dependency_overrides[_engine_coordinator] = lambda: coordinator
    return app


def _client(app: FastAPI) -> EngineClient:
    return EngineClient(
        EngineClientConfig(
            base_url="http://engine.test",
            service_token=_SERVICE_TOKEN,
            service_principal="codedock-backend",
            request_timeout_s=2,
            execution_timeout_s=10,
        ),
        transport=httpx.ASGITransport(app=app),
    )


def _command(
    context: ContextEnvelope,
    *,
    started: datetime,
):
    return command_from_context(
        context=context,
        actor_id="actor-a",
        capability="assistant.chat",
        idempotency_key="cross-service-idem",
        instructions="Follow the cross-service test policy.",
        prompt="Return a bounded answer.",
        objective="Cross-service engine boundary test",
        verification_profile="assistant_proposal",
        service_principal="codedock-backend",
        created_at=started,
        deadline=started + timedelta(seconds=10),
        trace_id="trace-cross-service",
        max_model_turns=2,
        max_tool_calls=1,
        max_repeat_tool_batches=1,
    )


class _GatedProvider:
    provider_id = "fake"
    model = "fake-model"
    available = True

    def __init__(self, gate: asyncio.Event) -> None:
        self.gate = gate
        self.requests = []

    async def generate(self, request):
        self.requests.append(request)
        await self.gate.wait()
        return ProviderResponse(
            text="late provider answer",
            provider=self.provider_id,
            model=self.model,
            request_id="late-request",
            response_id="late-response",
            finish_reason=FinishReason.COMPLETED,
            usage=ProviderUsage(
                input_tokens=5,
                output_tokens=3,
                total_tokens=8,
                usage_source="provider",
            ),
            context_id=request.context_id,
            context_digest=request.context_digest,
            context_source_snapshot=request.context_source_snapshot,
            context_compiler_version=request.context_compiler_version,
        )


class _Registry:
    def __init__(self, provider) -> None:
        self.provider = provider

    def require_active(self):
        return self.provider


class _GoldenProvider:
    provider_id = "fake"
    model = "fake-model"
    available = True

    def __init__(self) -> None:
        self.requests = []

    async def generate(self, request):
        self.requests.append(request)
        common = {
            "provider": self.provider_id,
            "model": self.model,
            "usage": ProviderUsage(
                input_tokens=7,
                output_tokens=4,
                total_tokens=11,
                usage_source="provider",
            ),
            "context_id": request.context_id,
            "context_digest": request.context_digest,
            "context_source_snapshot": request.context_source_snapshot,
            "context_compiler_version": request.context_compiler_version,
        }
        if len(self.requests) == 1:
            return ProviderResponse(
                text=None,
                request_id="golden-tool-request",
                response_id="golden-tool-response",
                tool_calls=(
                    ProviderToolCall(
                        call_id="call-read",
                        tool_id="repo.read",
                        arguments={"path": "README.md"},
                    ),
                ),
                finish_reason=FinishReason.TOOL_CALLS,
                **common,
            )
        if len(self.requests) == 2:
            return ProviderResponse(
                text="Verified repository answer.",
                request_id="golden-final-request",
                response_id="golden-final-response",
                finish_reason=FinishReason.COMPLETED,
                **common,
            )
        raise AssertionError("golden provider called more than twice")


def _golden_verification(_request, candidate, context_digest):
    assert candidate == "Verified repository answer."
    return ExecutionVerificationDecision(
        passed=True,
        receipt={
            "outcome": "passed",
            "policy_satisfied": True,
            "verifier_id": "test:http-golden",
            "candidate": "verified",
            "context_digest": context_digest,
        },
        evidence_refs=("evidence:http-golden-tool-result",),
    )


def _read_tool_definition() -> ProviderToolDefinition:
    return ProviderToolDefinition(
        tool_id="repo.read",
        description="Read one repository path.",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    )


def _read_tool_manifest() -> ToolManifest:
    return ToolManifest(
        tool_id="repo.read",
        version="1.0.0",
        description="Read one repository path.",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
        effect=ToolEffect.READ_ONLY,
        approval_required=False,
    )


@pytest.mark.asyncio
async def test_full_server_gate_defers_engine_auth_to_service_boundary(
    tmp_path,
) -> None:
    from skeleton.api.server import create_app

    service = _service(tmp_path)
    app = create_app()
    app.dependency_overrides[_engine_service] = lambda: service
    app.dependency_overrides[_engine_service_token] = lambda: _SERVICE_TOKEN
    app.dependency_overrides[_engine_coordinator] = lambda: None

    context = _context()
    command = _command(context, started=_now())
    client = _client(app)

    # No x-gf-seal is supplied by EngineClient. The production generic gate
    # must defer this exact prefix to the engine's bearer/principal authority.
    ack = await client.submit(command)
    assert ack["operation_id"] == context.operation_id
    assert ack["execution_id"] == context.execution_id

    bad_client = EngineClient(
        EngineClientConfig(
            base_url="http://engine.test",
            service_token="wrong-engine-token-" + ("x" * 40),
            service_principal="codedock-backend",
        ),
        transport=httpx.ASGITransport(app=app),
    )
    with pytest.raises(EngineAuthorizationError):
        await bad_client.status(
            context.execution_id,
            actor_id="actor-a",
            tenant_id="tenant-a",
        )


@pytest.mark.asyncio
async def test_backend_client_crosses_authenticated_engine_boundary_idempotently(
    tmp_path,
) -> None:
    service = _service(tmp_path)
    app = _app(service)
    client = _client(app)
    context = _context()

    first_started = _now()
    first = _command(context, started=first_started)
    ack = await client.submit(first)

    assert ack["operation_id"] == context.operation_id
    assert ack["execution_id"] == context.execution_id
    assert ack["state"] == "admitted"
    accepted_at = ack["accepted_at"]

    retry = _command(
        context,
        started=first_started + timedelta(seconds=1),
    )
    assert retry.command_digest != first.command_digest
    assert retry.submission_digest == first.submission_digest

    replay = await client.submit(retry)
    assert replay["operation_id"] == ack["operation_id"]
    assert replay["execution_id"] == ack["execution_id"]
    assert replay["idempotency_digest"] == ack["idempotency_digest"]
    assert replay["accepted_at"] == accepted_at

    status = await client.status(
        context.execution_id,
        actor_id="actor-a",
        tenant_id="tenant-a",
        trace_id="trace-status",
    )
    assert status["operation_id"] == context.operation_id
    assert status["execution_id"] == context.execution_id
    assert status["execution_state"] == "created"
    assert status["cancellation_requested"] is False

    with pytest.raises(EngineAuthorizationError):
        await client.status(
            context.execution_id,
            actor_id="actor-a",
            tenant_id="tenant-b",
        )

    cancelled = await client.cancel(
        context.execution_id,
        actor_id="actor-a",
        tenant_id="tenant-a",
        reason="cross-service cancellation test",
        trace_id="trace-cancel",
    )
    assert cancelled["operation_id"] == context.operation_id
    assert cancelled["execution_id"] == context.execution_id
    assert cancelled["cancellation_requested"] is True

    after = await client.status(
        context.execution_id,
        actor_id="actor-a",
        tenant_id="tenant-a",
    )
    assert after["cancellation_requested"] is True


@pytest.mark.asyncio
async def test_http_golden_journey_preserves_provider_tool_verification_lineage(
    tmp_path,
) -> None:
    service = _service(tmp_path)
    provider = _GoldenProvider()
    tools = AsyncToolRuntime()
    tool_effects = []

    async def read_handler(tool_request):
        tool_effects.append(
            (
                tool_request.tool_id,
                dict(tool_request.arguments),
                tool_request.operation_id,
            )
        )
        return "README evidence"

    await tools.register(_read_tool_manifest(), read_handler)
    coordinator = EngineExecutionCoordinator(
        service,
        provider_registry=_Registry(provider),
        tool_runtime=tools,
        verification_hook=_golden_verification,
    )
    app = _app(service, coordinator=coordinator)
    client = _client(app)
    context = _context()
    started = _now()
    command = command_from_context(
        context=context,
        actor_id="actor-a",
        capability="assistant.chat",
        idempotency_key="http-golden-idem",
        instructions="Use the read tool before answering.",
        prompt="Read README and answer.",
        objective="HTTP golden journey",
        verification_profile="evidence_required",
        service_principal="codedock-backend",
        created_at=started,
        deadline=started + timedelta(seconds=20),
        trace_id="trace-http-golden",
        max_model_turns=3,
        max_tool_calls=2,
        max_repeat_tool_batches=1,
        tools=(_read_tool_definition(),),
        tool_choice="auto",
    )

    result = await client.execute(command)

    assert result.operation_id == context.operation_id
    assert result.execution_id == context.execution_id
    assert result.final_output == "Verified repository answer."
    assert result.verification_receipt is not None
    assert result.verification_receipt["outcome"] == "passed"
    assert result.evidence_refs == ("evidence:http-golden-tool-result",)
    assert len(result.provider_receipts) == 2
    assert len(result.tool_receipts) == 1
    assert result.usage["model_turns"] == 2
    assert result.usage["tool_calls"] == 1
    assert len(provider.requests) == 2
    assert provider.requests[0].tools[0].tool_id == "repo.read"
    assert "Tool results from the previous provider turn" in provider.requests[1].prompt
    assert tool_effects
    assert tool_effects[0][0] == "repo.read"
    assert tool_effects[0][1] == {"path": "README.md"}

    turns = service.repository.turns(context.execution_id)
    assert len(turns) >= 3
    assert turns[0].execution_id == context.execution_id
    assert turns[-1].parent_turn_id is not None

    events = await client.events(
        context.execution_id,
        actor_id="actor-a",
        tenant_id="tenant-a",
    )
    event_types = [event["type"] for event in events["events"]]
    assert "execution.completed" in event_types

    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_http_cancel_fences_late_provider_result(tmp_path) -> None:
    service = _service(tmp_path)
    gate = asyncio.Event()
    provider = _GatedProvider(gate)
    coordinator = EngineExecutionCoordinator(
        service,
        provider_registry=_Registry(provider),
        tool_runtime=AsyncToolRuntime(),
    )
    app = _app(service, coordinator=coordinator)
    client = _client(app)
    context = _context()
    command = _command(context, started=_now())

    execute_task = asyncio.create_task(client.execute(command))
    for _ in range(100):
        if provider.requests:
            break
        await asyncio.sleep(0)
    else:
        execute_task.cancel()
        raise AssertionError("provider request did not start")

    cancelled = await client.cancel(
        context.execution_id,
        actor_id="actor-a",
        tenant_id="tenant-a",
        reason="HTTP cancel race",
    )
    assert cancelled["cancellation_requested"] is True

    gate.set()
    with pytest.raises(EngineExecutionFailed) as caught:
        await execute_task

    assert caught.value.execution_id == context.execution_id
    assert caught.value.status == "cancelled"
    assert caught.value.failure_code == "cancellation_requested"
    assert caught.value.result is not None
    assert caught.value.result["final_output"] is None

    checkpoint = service.repository.latest_checkpoint(
        context.execution_id
    )
    assert checkpoint is not None
    assert checkpoint.payload["last_provider"]["late_result_fenced"] is True
    assert (
        checkpoint.payload["last_provider"]["text"]
        == "late provider answer"
    )

    final_status = await client.status(
        context.execution_id,
        actor_id="actor-a",
        tenant_id="tenant-a",
    )
    assert final_status["execution_state"] == "cancelled"
    assert final_status["failure_code"] == "cancellation_requested"

    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_cross_service_principal_and_capability_denials_are_403_classified(
    tmp_path,
) -> None:
    service = _service(tmp_path)
    app = _app(service)
    context = _context()
    command = _command(context, started=_now())

    wrong_principal = EngineClient(
        EngineClientConfig(
            base_url="http://engine.test",
            service_token=_SERVICE_TOKEN,
            service_principal="untrusted-service",
        ),
        transport=httpx.ASGITransport(app=app),
    )
    with pytest.raises(EngineAuthorizationError):
        await wrong_principal.submit(command)

    # A valid principal may not submit a capability outside its server-side grant.
    admin_command = command_from_context(
        context=context,
        actor_id="actor-a",
        capability="assistant.compat",
        idempotency_key="wrong-capability",
        instructions="Policy.",
        prompt="Prompt.",
        verification_profile="assistant_proposal",
        service_principal="codedock-backend",
        created_at=_now(),
        deadline=_now() + timedelta(seconds=10),
    )
    with pytest.raises(EngineAuthorizationError):
        await _client(app).submit(admin_command)
