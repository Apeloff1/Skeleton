from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
from uuid import uuid4

from fastapi import FastAPI
import httpx
import pytest

from core.engine_client import (
    EngineAuthorizationError,
    EngineClient,
    EngineClientConfig,
    EngineProtocolError,
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
from skeleton.api.engine_runtime import EngineExecutionCoordinator
from skeleton.api.engine_service import (
    EngineExecutionService,
    SQLiteEngineSubmissionStore,
)
from skeleton.contracts.ai_execution import AIExecutionRequest
from skeleton.contracts.context import (
    ContextBudget,
    ContextEnvelope,
    ContextKind,
    ContextSegment,
    ContextTrust,
    context_digest_payload,
)
from skeleton.intelligence.execution_runtime import (
    ExecutionVerificationDecision,
)
from skeleton.persistence.execution_repository import (
    SQLiteExecutionRepository,
)
from skeleton.provider_contract import (
    FinishReason,
    ProviderToolCall,
    ProviderToolDefinition,
    ProviderUsage,
)
from skeleton.provider_runtime import ProviderResponse
from skeleton.skills.tool_contract import ToolEffect, ToolManifest
from skeleton.skills.tool_receipt_store import SQLiteToolReceiptStore
from skeleton.skills.tool_runtime import AsyncToolRuntime


_SERVICE_TOKEN = "cross-service-token-" + ("x" * 48)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _context(*, tenant_id: str = "tenant-a") -> ContextEnvelope:
    operation_id = str(uuid4())
    execution_id = str(uuid4())
    turn_id = str(uuid4())
    segment = ContextSegment.from_content(
        segment_id=str(uuid4()),
        kind=ContextKind.PRODUCT_INSTRUCTION,
        source_type="cross-service-policy",
        source_id="policy:cross-service",
        content="Answer through the canonical engine only.",
        trust_level=ContextTrust.TRUSTED_CONTROL,
        data_class="internal",
        tenant_id=tenant_id,
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
        tenant_id=tenant_id,
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
        tenant_id=tenant_id,
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


def _command(
    context: ContextEnvelope,
    *,
    capability: str = "assistant.chat",
    started: datetime | None = None,
    tools: tuple[ProviderToolDefinition, ...] = (),
):
    begun = started or _now()
    return command_from_context(
        context=context,
        actor_id="actor-a",
        capability=capability,
        idempotency_key="cross-service-idem",
        instructions="Answer through the canonical engine only.",
        prompt="Return the cross-service answer.",
        objective="Cross-service golden journey",
        verification_profile=(
            "evidence_required"
            if tools
            else "assistant_proposal"
        ),
        service_principal="backend-service",
        created_at=begun,
        deadline=begun + timedelta(minutes=2),
        trace_id="trace:" + context.operation_id,
        max_model_turns=2,
        max_tool_calls=1,
        max_repeat_tool_batches=1,
        tools=tools,
        tool_choice=("auto" if tools else "none"),
        context_seed_refs=("conversation:cross-service",),
    )


def _verified(
    _request: AIExecutionRequest,
    candidate: str,
    context_digest: str,
) -> ExecutionVerificationDecision:
    return ExecutionVerificationDecision(
        passed=True,
        receipt={
            "outcome": "passed",
            "policy_satisfied": True,
            "verifier_id": "test:cross-service",
            "candidate_digest": hashlib.sha256(
                candidate.encode("utf-8")
            ).hexdigest(),
            "context_digest": context_digest,
        },
        evidence_refs=("evidence:cross-service",),
    )


class _Provider:
    provider_id = "fake-engine-provider"
    model = "fake-engine-model"
    available = True

    def __init__(self, *, gate: asyncio.Event | None = None) -> None:
        self.gate = gate
        self.requests = []

    async def generate(self, request):
        self.requests.append(request)
        if self.gate is not None:
            await self.gate.wait()
        return ProviderResponse(
            text="cross-service answer",
            provider=self.provider_id,
            model=self.model,
            request_id="provider-request-1",
            response_id="provider-response-1",
            finish_reason=FinishReason.COMPLETED,
            usage=ProviderUsage(
                input_tokens=7,
                output_tokens=3,
                total_tokens=10,
                usage_source="provider",
            ),
            context_id=request.context_id,
            context_digest=request.context_digest,
            context_source_snapshot=request.context_source_snapshot,
            context_compiler_version=request.context_compiler_version,
        )


class _ToolProvider:
    provider_id = "fake-engine-provider"
    model = "fake-engine-model"
    available = True

    def __init__(self) -> None:
        self.requests = []

    async def generate(self, request):
        self.requests.append(request)
        common = {
            "provider": self.provider_id,
            "model": self.model,
            "context_id": request.context_id,
            "context_digest": request.context_digest,
            "context_source_snapshot": request.context_source_snapshot,
            "context_compiler_version": request.context_compiler_version,
        }
        if len(self.requests) == 1:
            return ProviderResponse(
                text=None,
                request_id="provider-tool-1",
                response_id="provider-tool-1",
                tool_calls=(
                    ProviderToolCall(
                        call_id="call-read-1",
                        tool_id="repo.read",
                        arguments={"path": "README.md"},
                    ),
                ),
                finish_reason=FinishReason.TOOL_CALLS,
                usage=ProviderUsage(
                    input_tokens=8,
                    output_tokens=3,
                    total_tokens=11,
                    usage_source="provider",
                ),
                **common,
            )
        if len(self.requests) == 2:
            return ProviderResponse(
                text="tool-grounded cross-service answer",
                request_id="provider-final-2",
                response_id="provider-final-2",
                finish_reason=FinishReason.COMPLETED,
                usage=ProviderUsage(
                    input_tokens=12,
                    output_tokens=4,
                    total_tokens=16,
                    usage_source="provider",
                ),
                **common,
            )
        raise AssertionError("provider executed more turns than expected")


class _ApprovalProvider:
    provider_id = "fake-engine-provider"
    model = "fake-engine-model"
    available = True

    def __init__(self) -> None:
        self.requests = []

    async def generate(self, request):
        self.requests.append(request)
        common = {
            "provider": self.provider_id,
            "model": self.model,
            "context_id": request.context_id,
            "context_digest": request.context_digest,
            "context_source_snapshot": request.context_source_snapshot,
            "context_compiler_version": request.context_compiler_version,
        }
        if len(self.requests) == 1:
            return ProviderResponse(
                text=None,
                request_id="provider-write-1",
                response_id="provider-write-1",
                tool_calls=(
                    ProviderToolCall(
                        call_id="call-write-1",
                        tool_id="repo.write",
                        arguments={"path": "README.md"},
                    ),
                ),
                finish_reason=FinishReason.TOOL_CALLS,
                usage=ProviderUsage(
                    input_tokens=9,
                    output_tokens=3,
                    total_tokens=12,
                    usage_source="provider",
                ),
                **common,
            )
        if len(self.requests) == 2:
            return ProviderResponse(
                text="approved write completed",
                request_id="provider-write-final-2",
                response_id="provider-write-final-2",
                finish_reason=FinishReason.COMPLETED,
                usage=ProviderUsage(
                    input_tokens=13,
                    output_tokens=4,
                    total_tokens=17,
                    usage_source="provider",
                ),
                **common,
            )
        raise AssertionError("approval provider executed too many turns")


class _Registry:
    def __init__(self, provider) -> None:
        self.provider = provider

    def require_active(self):
        return self.provider


def _boundary(
    tmp_path,
    provider,
    *,
    tool_runtime: AsyncToolRuntime | None = None,
):
    repository = SQLiteExecutionRepository(
        tmp_path / "cross-service-execution.sqlite3"
    )
    service = EngineExecutionService(
        repository,
        SQLiteEngineSubmissionStore(
            tmp_path / "cross-service-submission.sqlite3"
        ),
        EngineAuthorityRegistry(
            [
                EngineServiceGrant(
                    service_principal="backend-service",
                    scopes=frozenset(
                        {
                            "engine:submit",
                            "engine:read",
                            "engine:cancel",
                            "engine:events",
                            "engine:approve",
                            "engine:media",
                        }
                    ),
                    tenant_ids=frozenset({"tenant-a"}),
                    capabilities=frozenset(
                        {
                            "assistant.chat",
                            "media.image",
                            "media.speech",
                        }
                    ),
                )
            ]
        ),
    )
    coordinator = EngineExecutionCoordinator(
        service,
        provider_registry=_Registry(provider),
        tool_runtime=tool_runtime or AsyncToolRuntime(),
        verification_hook=_verified,
    )
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[_engine_service] = lambda: service
    app.dependency_overrides[_engine_service_token] = lambda: _SERVICE_TOKEN
    app.dependency_overrides[_engine_coordinator] = lambda: coordinator
    transport = httpx.ASGITransport(app=app)
    client = EngineClient(
        EngineClientConfig(
            base_url="http://engine.internal",
            service_token=_SERVICE_TOKEN,
            service_principal="backend-service",
            request_timeout_s=2,
            poll_interval_s=0.001,
            execution_timeout_s=2,
            max_poll_attempts=2000,
        ),
        transport=transport,
    )
    return service, coordinator, client


@pytest.mark.asyncio
async def test_cross_service_golden_journey_preserves_lineage(tmp_path) -> None:
    provider = _Provider()
    service, coordinator, client = _boundary(tmp_path, provider)
    context = _context()
    command = _command(context)

    terminal = await client.execute(command)

    assert terminal.status == "completed"
    assert terminal.operation_id == context.operation_id
    assert terminal.execution_id == context.execution_id
    assert terminal.final_output == "cross-service answer"
    assert terminal.verification is not None
    assert terminal.verification.startswith("verification:")
    assert terminal.verification_receipt["verifier_id"] == "test:cross-service"
    assert terminal.evidence_refs == ("evidence:cross-service",)
    assert len(provider.requests) == 1

    provider_request = provider.requests[0]
    assert provider_request.operation_id == context.operation_id
    assert provider_request.execution_id == context.execution_id
    assert provider_request.context_id == context.context_id
    assert provider_request.context_digest == context.context_digest
    assert (
        provider_request.context_source_snapshot
        == context.source_snapshot
    )
    assert (
        provider_request.context_compiler_version
        == context.compiler_version
    )

    events = await client.events(
        context.execution_id,
        actor_id="actor-a",
        tenant_id="tenant-a",
        trace_id=command.operation.trace_id,
    )
    result_events = [
        event
        for event in events["events"]
        if event.get("type") == "execution.result"
    ]
    assert len(result_events) == 1
    result = result_events[0]["result"]
    assert result["operation_id"] == context.operation_id
    assert result["execution_id"] == context.execution_id
    assert result["provider_receipts"]
    assert result["verification_receipt"]["policy_satisfied"] is True

    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_cross_service_golden_journey_preserves_tool_receipt_lineage(
    tmp_path,
) -> None:
    tool_calls = []
    tools = AsyncToolRuntime()

    async def read_handler(request):
        tool_calls.append(dict(request.arguments))
        return "artifact:readme"

    manifest = ToolManifest(
        tool_id="repo.read",
        version="1.0.0",
        description="Read a repository file.",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
        effect=ToolEffect.READ_ONLY,
    )
    await tools.register(manifest, read_handler)
    tool_definition = ProviderToolDefinition(
        tool_id=manifest.tool_id,
        description=manifest.description,
        input_schema=dict(manifest.input_schema),
    )
    provider = _ToolProvider()
    service, coordinator, client = _boundary(
        tmp_path,
        provider,
        tool_runtime=tools,
    )
    context = _context()
    command = _command(
        context,
        tools=(tool_definition,),
    )

    terminal = await client.execute(command)

    assert terminal.status == "completed"
    assert terminal.final_output == "tool-grounded cross-service answer"
    assert terminal.operation_id == context.operation_id
    assert terminal.execution_id == context.execution_id
    assert len(terminal.provider_receipts) == 2
    assert len(terminal.tool_receipts) == 1
    assert terminal.evidence_refs == ("evidence:cross-service",)
    assert terminal.usage["model_turns"] == 2
    assert terminal.usage["tool_calls"] == 1
    assert tool_calls == [{"path": "README.md"}]
    assert len(provider.requests) == 2
    assert provider.requests[0].tools[0].tool_id == "repo.read"
    assert provider.requests[0].tool_choice == "auto"
    assert provider.requests[1].prompt.startswith(
        "Tool results from the previous provider turn"
    )

    turns = service.repository.turns(context.execution_id)
    assert len(turns) == 3
    assert turns[0].provider_request_id == "provider-tool-1"
    assert turns[1].tool_receipt_ids
    assert turns[2].provider_request_id == "provider-final-2"

    events = await client.events(
        context.execution_id,
        actor_id="actor-a",
        tenant_id="tenant-a",
        trace_id=command.operation.trace_id,
    )
    result_events = [
        item
        for item in events["events"]
        if item.get("type") == "execution.result"
    ]
    assert result_events[-1]["result"]["tool_receipts"] == list(
        terminal.tool_receipts
    )
    assert result_events[-1]["result"]["provider_receipts"] == list(
        terminal.provider_receipts
    )

    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_cross_service_approval_gate_resumes_once_with_bound_receipt(
    tmp_path,
) -> None:
    effects = []
    tools = AsyncToolRuntime(
        receipt_store=SQLiteToolReceiptStore(
            tmp_path / "cross-service-tool-receipts.sqlite3"
        )
    )

    async def write_handler(request):
        effects.append(
            {
                "arguments": dict(request.arguments),
                "approval_ref": request.approval_ref,
            }
        )
        return "artifact:approved-write"

    manifest = ToolManifest(
        tool_id="repo.write",
        version="1.0.0",
        description="Write one repository file.",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
        effect=ToolEffect.REVERSIBLE,
        approval_required=True,
    )
    await tools.register(manifest, write_handler)
    tool_definition = ProviderToolDefinition(
        tool_id=manifest.tool_id,
        description=manifest.description,
        input_schema=dict(manifest.input_schema),
    )
    provider = _ApprovalProvider()
    service, coordinator, client = _boundary(
        tmp_path,
        provider,
        tool_runtime=tools,
    )
    context = _context()
    command = _command(
        context,
        tools=(tool_definition,),
    )
    assert "engine:approve" in command.delegated_authority.scopes

    await client.submit(command)

    pending = ()
    for _ in range(200):
        pending = await client.pending_tool_approvals(
            context.execution_id,
            actor_id="actor-a",
            tenant_id="tenant-a",
            trace_id=command.operation.trace_id,
        )
        if pending:
            break
        await asyncio.sleep(0)
    assert len(pending) == 1
    row = pending[0]
    assert row["call_id"] == "call-write-1"
    assert row["tool_id"] == "repo.write"
    assert row["approval_ref"].startswith("approval:")
    assert effects == []

    with pytest.raises(EngineProtocolError):
        await client.approve_tool_call(
            context.execution_id,
            actor_id="actor-a",
            tenant_id="tenant-a",
            call_id=row["call_id"],
            tool_id=row["tool_id"],
            arguments_digest="0" * 64,
            idempotency_key=row["idempotency_key"],
            expires_at=_now() + timedelta(seconds=30),
            trace_id=command.operation.trace_id,
        )
    assert effects == []

    approval = await client.approve_tool_call(
        context.execution_id,
        actor_id="actor-a",
        tenant_id="tenant-a",
        call_id=row["call_id"],
        tool_id=row["tool_id"],
        arguments_digest=row["arguments_digest"],
        idempotency_key=row["idempotency_key"],
        expires_at=_now() + timedelta(seconds=30),
        trace_id=command.operation.trace_id,
    )
    assert approval["approval_ref"] == row["approval_ref"]

    terminal = await client.wait_for_terminal(
        execution_id=context.execution_id,
        actor_id="actor-a",
        tenant_id="tenant-a",
        trace_id=command.operation.trace_id,
        timeout_s=2,
    )

    assert terminal.status == "completed"
    assert terminal.final_output == "approved write completed"
    assert len(terminal.tool_receipts) == 1
    assert len(terminal.provider_receipts) == 2
    assert len(effects) == 1
    assert effects[0]["arguments"] == {"path": "README.md"}
    assert effects[0]["approval_ref"] == row["approval_ref"]
    assert terminal.usage["model_turns"] == 2
    assert terminal.usage["tool_calls"] == 1
    assert len(provider.requests) == 2

    stored = service.repository.result(context.execution_id)
    assert stored is not None
    assert stored.tool_receipts == terminal.tool_receipts

    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_cross_service_submit_retry_rotates_authority_without_duplicate_work(
    tmp_path,
) -> None:
    gate = asyncio.Event()
    provider = _Provider(gate=gate)
    service, coordinator, client = _boundary(tmp_path, provider)
    context = _context()
    first_started = _now() - timedelta(seconds=30)
    first = _command(context, started=first_started)

    first_ack = await client.submit(first)
    await asyncio.sleep(0)

    retry = _command(
        context,
        started=_now(),
    )
    assert retry.command_digest != first.command_digest
    assert retry.submission_digest == first.submission_digest

    replay_ack = await client.submit(retry)
    assert replay_ack == first_ack
    await asyncio.sleep(0)
    assert len(provider.requests) == 1

    gate.set()
    terminal = await client.wait_for_terminal(
        execution_id=context.execution_id,
        actor_id="actor-a",
        tenant_id="tenant-a",
        trace_id=first.operation.trace_id,
        timeout_s=2,
    )
    assert terminal.status == "completed"
    assert len(provider.requests) == 1

    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_cross_service_denies_wrong_tenant_capability_and_token(
    tmp_path,
) -> None:
    provider = _Provider()
    service, coordinator, client = _boundary(tmp_path, provider)

    tenant_b = _context(tenant_id="tenant-b")
    with pytest.raises(EngineAuthorizationError):
        await client.submit(_command(tenant_b))

    tenant_a = _context()
    with pytest.raises(EngineAuthorizationError):
        await client.submit(
            _command(
                tenant_a,
                capability="assistant.compat",
            )
        )

    wrong_token = EngineClient(
        EngineClientConfig(
            base_url="http://engine.internal",
            service_token="wrong-token-" + ("z" * 40),
            service_principal="backend-service",
            request_timeout_s=2,
        ),
        transport=client._transport,
    )
    with pytest.raises(EngineAuthorizationError):
        await wrong_token.submit(_command(_context()))

    assert provider.requests == []
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_cross_service_cancel_fences_late_provider_result(
    tmp_path,
) -> None:
    gate = asyncio.Event()
    provider = _Provider(gate=gate)
    service, coordinator, client = _boundary(tmp_path, provider)
    context = _context()
    command = _command(context)

    await client.submit(command)
    for _ in range(100):
        if provider.requests:
            break
        await asyncio.sleep(0)
    assert len(provider.requests) == 1

    cancelled = await client.cancel(
        context.execution_id,
        actor_id="actor-a",
        tenant_id="tenant-a",
        reason="user cancelled",
        trace_id=command.operation.trace_id,
    )
    assert cancelled["cancellation_requested"] is True
    assert cancelled["execution_state"] != "completed"

    gate.set()
    for _ in range(100):
        await asyncio.sleep(0)
        status = await client.status(
            context.execution_id,
            actor_id="actor-a",
            tenant_id="tenant-a",
            trace_id=command.operation.trace_id,
        )
        if status["execution_state"] == "cancelled":
            break

    status = await client.status(
        context.execution_id,
        actor_id="actor-a",
        tenant_id="tenant-a",
        trace_id=command.operation.trace_id,
    )
    assert status["execution_state"] == "cancelled"

    result = service.repository.result(context.execution_id)
    assert result is not None
    assert result.status == "cancelled"
    assert result.final_output is None
    assert result.provider_receipts == (
        "provider:fake-engine-provider:provider-response-1",
    )
    assert result.usage["provider_usage"][0]["total_tokens"] == 10

    events = await client.events(
        context.execution_id,
        actor_id="actor-a",
        tenant_id="tenant-a",
        trace_id=command.operation.trace_id,
    )
    terminal_results = [
        event["result"]
        for event in events["events"]
        if event.get("type") == "execution.result"
    ]
    assert terminal_results[-1]["status"] == "cancelled"
    assert all(
        item["status"] != "completed"
        for item in terminal_results
    )

    await coordinator.shutdown()
