from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from core.engine_client import (
    EngineAuthorizationError,
    EngineClient,
    EngineClientConfig,
    EngineConflictError,
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
from skeleton.contracts.ai_execution import AIExecutionResult, ExecutionState
from skeleton.contracts.context import (
    ContextBudget,
    ContextEnvelope,
    ContextKind,
    ContextSegment,
    ContextTrust,
    context_digest_payload,
)
from skeleton.persistence.execution_repository import (
    ExecutionRepositoryConflict,
    SQLiteExecutionRepository,
)
from skeleton.provider_contract import ProviderArchitectureReceipt
from skeleton.provider_runtime import ProviderRegistry, ProviderResponse


_SERVICE_TOKEN = "cross-service-engine-token-" + ("x" * 48)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _context(*, tenant_id: str = "tenant-a") -> ContextEnvelope:
    operation_id = str(uuid4())
    execution_id = str(uuid4())
    turn_id = str(uuid4())
    segment = ContextSegment.from_content(
        segment_id=str(uuid4()),
        kind=ContextKind.PRODUCT_INSTRUCTION,
        source_type="cross-service-test-policy",
        source_id="policy:cross-service",
        content="Answer as a bounded assistant proposal.",
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
    *,
    context: ContextEnvelope | None = None,
    actor_id: str = "user-a",
    idempotency_key: str = "cross-service-idem",
    prompt: str = "Give one safe proposal.",
    started: datetime | None = None,
):
    envelope = context or _context()
    instant = started or _now()
    return command_from_context(
        context=envelope,
        actor_id=actor_id,
        capability="assistant.chat",
        idempotency_key=idempotency_key,
        instructions="Answer as a bounded assistant proposal.",
        prompt=prompt,
        objective="Complete one cross-service assistant turn",
        verification_profile="assistant_proposal",
        service_principal="backend-service",
        created_at=instant,
        deadline=instant + timedelta(minutes=2),
        trace_id="cross-service:" + envelope.operation_id,
        max_model_turns=2,
        max_tool_calls=1,
        max_repeat_tool_batches=1,
        context_seed_refs=("cross-service:test",),
    )


def _grant(
    *,
    scopes: frozenset[str] | None = None,
    tenants: frozenset[str] | None = None,
    capabilities: frozenset[str] | None = None,
) -> EngineServiceGrant:
    return EngineServiceGrant(
        service_principal="backend-service",
        scopes=scopes
        or frozenset(
            {
                "engine:submit",
                "engine:read",
                "engine:cancel",
                "engine:events",
                "engine:approve",
                "engine:media",
            }
        ),
        tenant_ids=tenants or frozenset({"tenant-a"}),
        capabilities=capabilities
        or frozenset(
            {
                "assistant.chat",
                "assistant.compat",
                "media.image",
                "media.speech",
            }
        ),
    )


def _service(tmp_path, *, grant: EngineServiceGrant | None = None):
    repository = SQLiteExecutionRepository(
        tmp_path / ("execution-" + str(uuid4()) + ".sqlite3")
    )
    submissions = SQLiteEngineSubmissionStore(
        tmp_path / ("submission-" + str(uuid4()) + ".sqlite3")
    )
    service = EngineExecutionService(
        repository,
        submissions,
        EngineAuthorityRegistry([grant or _grant()]),
    )
    return service


def _app(service, *, coordinator=None) -> FastAPI:
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
            service_principal="backend-service",
            request_timeout_s=2,
            poll_interval_s=0.001,
            execution_timeout_s=3,
        ),
        transport=httpx.ASGITransport(app=app),
    )


class _DeterministicProvider:
    provider_id = "deterministic-test"
    model = "deterministic-v1"

    def __init__(self) -> None:
        self.requests = []

    @property
    def available(self) -> bool:
        return True

    async def generate(self, request):
        self.requests.append(request)
        return ProviderResponse(
            text="golden engine answer",
            provider=self.provider_id,
            model=self.model,
            request_id="provider-request-1",
            response_id="provider-response-1",
            context_id=request.context_id,
            context_digest=request.context_digest,
            context_source_snapshot=request.context_source_snapshot,
            context_compiler_version=request.context_compiler_version,
        )


def _registry(provider: _DeterministicProvider) -> ProviderRegistry:
    receipt = ProviderArchitectureReceipt(
        provider_id=provider.provider_id,
        architecture_tag="arch-map/test",
        construction_version="cross-service-test",
        contract_digest="0" * 64,
        manual_path="docs/AI_APP_CONSTRUCTION_MANUAL.md",
        required_documents=("machine/architecture.json",),
    )
    return ProviderRegistry(
        [provider],
        active=provider.provider_id,
        architecture_loader=lambda _provider_id: receipt,
    )


@pytest.mark.asyncio
async def test_cross_service_retry_reuses_execution_with_fresh_delegation(
    tmp_path,
) -> None:
    service = _service(tmp_path)
    client = _client(_app(service))
    context = _context()
    started = _now()
    first = _command(context=context, started=started)
    retry = _command(
        context=context,
        started=started + timedelta(seconds=30),
    )

    assert first.command_digest != retry.command_digest
    assert first.submission_digest == retry.submission_digest

    first_ack = await client.submit(first)
    retry_ack = await client.submit(retry)

    assert retry_ack == first_ack
    assert retry_ack["execution_id"] == context.execution_id
    status = await client.status(
        context.execution_id,
        actor_id="user-a",
        tenant_id="tenant-a",
    )
    assert status["execution_state"] == ExecutionState.CREATED.value

    changed = _command(
        context=context,
        started=started + timedelta(seconds=45),
        prompt="Different semantic work.",
    )
    with pytest.raises(EngineConflictError):
        await client.submit(changed)


@pytest.mark.asyncio
async def test_cross_service_denies_actor_tenant_and_scope_spoofing(
    tmp_path,
) -> None:
    service = _service(tmp_path)
    app = _app(service)
    client = _client(app)
    command = _command()

    with pytest.raises(EngineAuthorizationError):
        await client._request(
            "POST",
            "/executions",
            json_body={
                "actor_id": "user-b",
                "tenant_id": "tenant-a",
                "command": command.as_dict(),
            },
        )

    tenant_b = _command(context=_context(tenant_id="tenant-b"))
    with pytest.raises(EngineAuthorizationError):
        await client.submit(tenant_b)

    no_submit_service = _service(
        tmp_path,
        grant=_grant(
            scopes=frozenset(
                {
                    "engine:read",
                    "engine:cancel",
                    "engine:events",
                }
            )
        ),
    )
    no_submit_client = _client(_app(no_submit_service))
    with pytest.raises(EngineAuthorizationError):
        await no_submit_client.submit(_command())


@pytest.mark.asyncio
async def test_cross_service_cancel_fences_late_success_commit(tmp_path) -> None:
    service = _service(tmp_path)
    client = _client(_app(service))
    command = _command()

    ack = await client.submit(command)
    cancelled = await client.cancel(
        ack["execution_id"],
        actor_id=command.operation.actor_id,
        tenant_id=command.operation.tenant_id,
        reason="user cancelled",
    )
    assert cancelled["cancellation_requested"] is True

    current = service.repository.get(ack["execution_id"])
    assert current.cancellation_requested is True

    late_result = AIExecutionResult(
        operation_id=command.operation.operation_id,
        execution_id=ack["execution_id"],
        status="completed",
        final_output="late success must not land",
        verification="verification:late",
        usage={"model_turns": 1, "tool_calls": 0},
        stream_terminal_event="stream-terminal:late-success",
        completed_at=_now(),
    )
    with pytest.raises(
        ExecutionRepositoryConflict,
        match="fenced after cancellation request",
    ):
        service.repository.finalize(
            late_result,
            expected_execution_version=current.version,
            now=_now(),
        )

    cancelled_result = AIExecutionResult(
        operation_id=command.operation.operation_id,
        execution_id=ack["execution_id"],
        status="cancelled",
        usage={"model_turns": 0, "tool_calls": 0},
        stream_terminal_event="stream-terminal:cancelled",
        completed_at=_now(),
    )
    terminal = service.repository.finalize(
        cancelled_result,
        expected_execution_version=current.version,
        now=_now(),
    )
    assert terminal.state is ExecutionState.CANCELLED

    status = await client.status(
        ack["execution_id"],
        actor_id=command.operation.actor_id,
        tenant_id=command.operation.tenant_id,
    )
    assert status["execution_state"] == ExecutionState.CANCELLED.value
    assert status["cancellation_requested"] is True


@pytest.mark.asyncio
async def test_cross_service_golden_prompt_preserves_lineage(tmp_path) -> None:
    service = _service(tmp_path)
    provider = _DeterministicProvider()
    coordinator = EngineExecutionCoordinator(
        service,
        provider_registry=_registry(provider),
    )
    client = _client(_app(service, coordinator=coordinator))
    command = _command()

    try:
        result = await client.execute(command)
        events = await client.events(
            result.execution_id,
            actor_id=command.operation.actor_id,
            tenant_id=command.operation.tenant_id,
            trace_id=command.operation.trace_id,
        )
    finally:
        await coordinator.shutdown()

    assert result.status == "completed"
    assert result.operation_id == command.operation.operation_id
    assert result.execution_id == command.execution_request.execution_id
    assert result.final_output == "golden engine answer"
    assert result.verification is not None
    assert result.provider_receipts
    assert provider.requests

    provider_request = provider.requests[0]
    assert provider_request.operation_id == command.operation.operation_id
    assert provider_request.execution_id == command.execution_request.execution_id
    assert provider_request.context_id == command.compiled_context.context_id
    assert provider_request.context_digest == command.compiled_context.context_digest
    assert provider_request.context_source_snapshot == (
        command.compiled_context.source_snapshot
    )
    assert provider_request.context_compiler_version == (
        command.compiled_context.compiler_version
    )

    event_types = [event["type"] for event in events["events"]]
    assert event_types[0] == "execution.state"
    assert "execution.turn" in event_types
    assert "execution.checkpoint" in event_types
    assert "execution.result" in event_types
    assert "execution.completed" in event_types

    turn_events = [
        event
        for event in events["events"]
        if event["type"] == "execution.turn"
    ]
    assert turn_events
    first_turn = turn_events[0]["turn"]
    assert first_turn["operation_id"] == command.operation.operation_id
    assert first_turn["execution_id"] == command.execution_request.execution_id
    assert first_turn["context_digest"] == command.compiled_context.context_digest
    assert first_turn["provider_request_id"] == "provider-request-1"
    assert first_turn["provider_response_id"] == "provider-response-1"

    result_events = [
        event
        for event in events["events"]
        if event["type"] == "execution.result"
    ]
    assert len(result_events) == 1
    terminal_payload = result_events[0]["result"]
    assert terminal_payload["operation_id"] == command.operation.operation_id
    assert terminal_payload["execution_id"] == command.execution_request.execution_id
    assert terminal_payload["final_output"] == "golden engine answer"
    assert terminal_payload["verification_receipt"]["policy_satisfied"] is True
    assert terminal_payload["provider_receipts"]
