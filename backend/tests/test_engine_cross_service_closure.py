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
    EngineClientConfig,
    EngineExecutionFailed,
    command_from_context,
)
from skeleton.api.engine_authority import (
    DelegatedAuthority,
    EngineAuthorityRegistry,
    EngineServiceGrant,
    engine_request_binding,
)
from skeleton.api.engine_routes import (
    _engine_coordinator,
    _engine_service,
    _engine_service_token,
    router,
)
from skeleton.api.engine_runtime import EngineExecutionCoordinator
from skeleton.api.engine_service import (
    EngineExecutionCommand,
    EngineExecutionService,
    SQLiteEngineSubmissionStore,
)
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


_SERVICE_TOKEN = "closure-engine-service-token-" + ("x" * 48)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _context(
    *,
    tenant_id: str = "tenant-a",
    operation_id: str | None = None,
    execution_id: str | None = None,
    turn_id: str | None = None,
) -> ContextEnvelope:
    operation_id = operation_id or str(uuid4())
    execution_id = execution_id or str(uuid4())
    turn_id = turn_id or str(uuid4())
    segment = ContextSegment.from_content(
        segment_id=str(uuid4()),
        kind=ContextKind.PRODUCT_INSTRUCTION,
        source_type="closure-test-policy",
        source_id="policy:engine-closure",
        content="Follow the canonical closure-test instruction.",
        trust_level=ContextTrust.TRUSTED_CONTROL,
        data_class="internal",
        tenant_id=tenant_id,
        purpose="model-inference",
        priority=1000,
        relevance=1.0,
        created_at=_now(),
        provenance=("engine-closure-test",),
        retention_class="policy",
        mandatory=True,
    )
    budget = ContextBudget(
        max_context_tokens=8192,
        reserved_output_tokens=1024,
        reserved_tool_result_tokens=1024,
        reserved_policy_tokens=1024,
        safety_margin_tokens=256,
        max_segment_tokens=4096,
        max_artifact_tokens=2048,
        max_tool_result_tokens=2048,
    )
    digest = context_digest_payload(
        operation_id=operation_id,
        execution_id=execution_id,
        turn_id=turn_id,
        tenant_id=tenant_id,
        budget=budget,
        selected=(segment,),
        omitted_segment_ids=(),
        compiler_version="closure-test-v1",
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
        compiler_version="closure-test-v1",
    )


def _command(
    context: ContextEnvelope,
    *,
    actor_id: str = "actor-a",
    capability: str = "assistant.chat",
    idempotency_key: str = "closure-idem",
    created_at: datetime | None = None,
    deadline: datetime | None = None,
    tools: tuple[ProviderToolDefinition, ...] = (),
    verification_profile: str = "assistant_proposal",
) -> EngineExecutionCommand:
    started = created_at or _now()
    return command_from_context(
        context=context,
        actor_id=actor_id,
        capability=capability,
        idempotency_key=idempotency_key,
        instructions="Follow the canonical closure-test instruction.",
        prompt="Complete the closure-test request.",
        objective="Prove the engine application boundary.",
        verification_profile=verification_profile,
        service_principal="backend-service",
        created_at=started,
        deadline=deadline or (started + timedelta(minutes=2)),
        trace_id="closure:" + context.operation_id,
        max_model_turns=4,
        max_tool_calls=4,
        max_repeat_tool_batches=1,
        tools=tools,
        tool_choice="auto" if tools else "none",
        context_seed_refs=(
            "turn:" + context.turn_id,
            "context:" + context.context_id,
        ),
    )


def _service(tmp_path) -> EngineExecutionService:
    authorities = EngineAuthorityRegistry(
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
                        "assistant.compat",
                        "media.image",
                        "media.speech",
                    }
                ),
            )
        ]
    )
    return EngineExecutionService(
        SQLiteExecutionRepository(tmp_path / "closure-execution.sqlite3"),
        SQLiteEngineSubmissionStore(tmp_path / "closure-submission.sqlite3"),
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


def _client(
    app: FastAPI,
    *,
    token: str = _SERVICE_TOKEN,
) -> EngineClient:
    return EngineClient(
        EngineClientConfig(
            base_url="http://engine.test",
            service_token=token,
            service_principal="backend-service",
            request_timeout_s=2,
            poll_interval_s=0.001,
            execution_timeout_s=5,
            max_poll_attempts=5000,
        ),
        transport=httpx.ASGITransport(app=app),
    )


class _Registry:
    def __init__(self, provider) -> None:
        self._provider = provider

    def require_active(self):
        return self._provider


def _text_response(text: str, *, response_id: str) -> ProviderResponse:
    return ProviderResponse(
        text=text,
        provider="fake",
        model="fake-model",
        request_id=response_id,
        response_id=response_id,
        finish_reason=FinishReason.COMPLETED,
        usage=ProviderUsage(
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            usage_source="provider",
        ),
    )


def _tool_response(
    *,
    response_id: str = "resp-tool",
) -> ProviderResponse:
    return ProviderResponse(
        text=None,
        provider="fake",
        model="fake-model",
        request_id=response_id,
        response_id=response_id,
        tool_calls=(
            ProviderToolCall(
                call_id="call-readme",
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
    )


def _verification(_request, candidate, _context_digest):
    assert candidate
    return ExecutionVerificationDecision(
        passed=True,
        receipt={
            "outcome": "passed",
            "policy_satisfied": True,
            "verifier_id": "closure-test:independent",
        },
        evidence_refs=("evidence:closure-test",),
    )


@pytest.mark.asyncio
async def test_cross_service_authenticated_submit_query_and_retry_are_idempotent(
    tmp_path,
) -> None:
    service = _service(tmp_path)
    app = _app(service)
    client = _client(app)
    context = _context()

    started = _now()
    first = _command(
        context,
        idempotency_key="retry-same-work",
        created_at=started,
        deadline=started + timedelta(minutes=2),
    )
    first_ack = await client.submit(first)

    retry_started = started + timedelta(seconds=30)
    retry = _command(
        context,
        idempotency_key="retry-same-work",
        created_at=retry_started,
        deadline=retry_started + timedelta(minutes=2),
    )
    assert retry.command_digest != first.command_digest
    assert retry.submission_digest == first.submission_digest

    retry_ack = await client.submit(retry)
    assert retry_ack == first_ack

    status = await client.status(
        context.execution_id,
        actor_id="actor-a",
        tenant_id="tenant-a",
        trace_id="closure-query",
    )
    assert status["execution_id"] == context.execution_id
    assert status["operation_id"] == context.operation_id
    assert status["execution_state"] == "created"

    stored = service.submissions.get_by_execution_id(context.execution_id)
    assert stored is not None
    assert stored.ack.as_dict() == first_ack


@pytest.mark.asyncio
async def test_cross_service_rejects_bad_token_and_delegated_actor_tenant_scope(
    tmp_path,
) -> None:
    service = _service(tmp_path)
    app = _app(service)
    context = _context()
    valid = _command(context)

    with pytest.raises(EngineAuthorizationError):
        await _client(
            app,
            token="wrong-token-" + ("z" * 40),
        ).submit(valid)

    def replace_authority(**changes):
        source = valid.delegated_authority
        authority = DelegatedAuthority(
            service_principal=changes.get(
                "service_principal",
                source.service_principal,
            ),
            actor_id=changes.get("actor_id", source.actor_id),
            tenant_id=changes.get("tenant_id", source.tenant_id),
            scopes=changes.get("scopes", source.scopes),
            capability=changes.get("capability", source.capability),
            issued_at=source.issued_at,
            expires_at=source.expires_at,
            request_binding=engine_request_binding(
                valid.operation,
                valid.execution_request,
            ),
        )
        return EngineExecutionCommand(
            operation=valid.operation,
            execution_request=valid.execution_request,
            delegated_authority=authority,
            compiled_context=valid.compiled_context,
            context_seed_refs=valid.context_seed_refs,
            resource_budget=valid.resource_budget,
            stream_preferences=valid.stream_preferences,
        )

    for denied in (
        replace_authority(actor_id="actor-b"),
        replace_authority(tenant_id="tenant-b"),
        replace_authority(
            scopes=(
                "engine:read",
                "engine:cancel",
                "engine:events",
            )
        ),
    ):
        with pytest.raises(EngineAuthorizationError):
            await _client(app).submit(denied)

    assert service.submissions.get_by_execution_id(
        context.execution_id
    ) is None


@pytest.mark.asyncio
async def test_cross_service_cancel_fences_late_provider_result(
    tmp_path,
) -> None:
    service = _service(tmp_path)
    started = asyncio.Event()
    release = asyncio.Event()

    class GateProvider:
        provider_id = "fake"
        model = "fake-model"

        async def generate(self, _request):
            started.set()
            await release.wait()
            return _text_response(
                "must-not-become-final-output",
                response_id="resp-late-cancel",
            )

    coordinator = EngineExecutionCoordinator(
        service,
        provider_registry=_Registry(GateProvider()),
        verification_hook=_verification,
    )
    app = _app(service, coordinator=coordinator)
    client = _client(app)
    context = _context()
    command = _command(context)

    await client.submit(command)
    await asyncio.wait_for(started.wait(), timeout=2)

    cancelled = await client.cancel(
        context.execution_id,
        actor_id="actor-a",
        tenant_id="tenant-a",
        reason="closure-test cancellation",
        trace_id="closure-cancel",
    )
    assert cancelled["cancellation_requested"] is True

    release.set()

    for _ in range(1000):
        current = await client.status(
            context.execution_id,
            actor_id="actor-a",
            tenant_id="tenant-a",
        )
        if current["execution_state"] == "cancelled":
            break
        await asyncio.sleep(0.001)
    else:
        raise AssertionError("cancelled execution did not reach terminal state")

    result = service.repository.result(context.execution_id)
    assert result is not None
    assert result.status == "cancelled"
    assert result.final_output is None
    assert result.usage["error_code"] == "cancellation_requested"
    assert result.provider_receipts == (
        "provider:fake:resp-late-cancel",
    )
    checkpoint = service.repository.latest_checkpoint(
        context.execution_id
    )
    assert checkpoint is not None
    assert checkpoint.payload["last_provider"]["late_result_fenced"] is True

    with pytest.raises(EngineExecutionFailed) as caught:
        await client.wait_for_terminal(
            execution_id=context.execution_id,
            actor_id="actor-a",
            tenant_id="tenant-a",
            timeout_s=2,
        )
    assert caught.value.status == "cancelled"
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_cross_service_golden_journey_preserves_receipt_lineage(
    tmp_path,
) -> None:
    service = _service(tmp_path)

    class GoldenProvider:
        provider_id = "fake"
        model = "fake-model"

        def __init__(self) -> None:
            self.responses = [
                _tool_response(),
                _text_response(
                    "Golden answer",
                    response_id="resp-final",
                ),
            ]

        async def generate(self, _request):
            if not self.responses:
                raise AssertionError("unexpected extra provider turn")
            return self.responses.pop(0)

    tools = AsyncToolRuntime()

    async def read_handler(_request):
        return "artifact:readme"

    await tools.register(
        ToolManifest(
            tool_id="repo.read",
            version="1.0.0",
            description="Read repository data",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
            effect=ToolEffect.READ_ONLY,
            approval_required=False,
        ),
        read_handler,
    )
    coordinator = EngineExecutionCoordinator(
        service,
        provider_registry=_Registry(GoldenProvider()),
        tool_runtime=tools,
        verification_hook=_verification,
    )
    app = _app(service, coordinator=coordinator)
    client = _client(app)

    context = _context()
    tool = ProviderToolDefinition(
        tool_id="repo.read",
        description="Read repository data",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    )
    command = _command(
        context,
        tools=(tool,),
        verification_profile="evidence_required",
    )

    result = await client.execute(command)

    assert result.operation_id == context.operation_id
    assert result.execution_id == context.execution_id
    assert result.final_output == "Golden answer"
    assert result.verification is not None
    assert result.verification_receipt is not None
    assert result.verification_receipt["outcome"] == "passed"
    assert result.evidence_refs == ("evidence:closure-test",)
    assert result.provider_receipts == (
        "provider:fake:resp-tool",
        "provider:fake:resp-final",
    )
    assert len(result.tool_receipts) == 1
    assert result.stream_terminal_event is not None

    events = await client.events(
        context.execution_id,
        actor_id="actor-a",
        tenant_id="tenant-a",
    )
    terminal = [
        event
        for event in events["events"]
        if event["type"] == "execution.result"
    ]
    assert len(terminal) == 1
    payload = terminal[0]["result"]
    assert payload["operation_id"] == context.operation_id
    assert payload["execution_id"] == context.execution_id
    assert payload["tool_receipts"] == list(result.tool_receipts)
    assert payload["provider_receipts"] == list(
        result.provider_receipts
    )
    assert command.compiled_context.turn_id == context.turn_id

    await coordinator.shutdown()
