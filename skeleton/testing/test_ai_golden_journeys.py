"""Deterministic Stage-7 AI golden journeys.

This suite deliberately avoids live provider credentials.  It assembles the
canonical execution coordinator, durable execution state, provider-neutral
responses, governed tool runtime, durable tool receipts, retrieval pipeline,
verification evidence, and terminal operation events in one test seam.

The tests are release evidence, not authority: machine closure/signoff remains
open until the independent verification and browser/deployed journeys required
by the masterplan are green.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
from uuid import uuid4

import pytest

from skeleton.api.engine_authority import (
    DelegatedAuthority,
    EngineAuthorityRegistry,
    EngineServiceGrant,
    engine_request_binding,
)
from skeleton.api.engine_runtime import EngineExecutionCoordinator
from skeleton.api.engine_service import (
    EngineContextHandoff,
    EngineExecutionCommand,
    EngineExecutionService,
    EngineSubmissionConflict,
    SQLiteEngineSubmissionStore,
)
from skeleton.api.server import ServerState
from skeleton.contracts.ai_execution import AIExecutionRequest
from skeleton.contracts.operation import OperationEnvelope
from skeleton.intelligence.execution_runtime import ExecutionVerificationDecision
from skeleton.persistence.execution_repository import SQLiteExecutionRepository
from skeleton.provider_contract import (
    FinishReason,
    ProviderToolCall,
    ProviderToolDefinition,
    ProviderUsage,
    provider_arguments_digest,
)
from skeleton.provider_runtime import ProviderResponse, ProviderUnavailableError
from skeleton.retrieval.fusion import ScoredResult
from skeleton.retrieval.pipeline import SearchPipeline
from skeleton.retrieval.query import QueryPlanner
from skeleton.skills.tool_contract import (
    ToolEffect,
    ToolExecutionRequest,
    ToolExecutionStatus,
    ToolManifest,
)
from skeleton.skills.tool_receipt_store import SQLiteToolReceiptStore
from skeleton.skills.tool_runtime import AsyncToolRuntime


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _verification(
    _request: AIExecutionRequest,
    candidate: str,
    context_digest: str,
) -> ExecutionVerificationDecision:
    return ExecutionVerificationDecision(
        passed=True,
        receipt={
            "outcome": "passed",
            "policy_satisfied": True,
            "verifier_id": "stage7:deterministic-independent-verifier",
            "candidate_digest": hashlib.sha256(
                candidate.encode("utf-8")
            ).hexdigest(),
            "context_digest": context_digest,
        },
        evidence_refs=("evidence:stage7-golden-journey",),
    )


class _SequenceProvider:
    provider_id = "deterministic"
    model = "fixture-model"
    available = True

    def __init__(self, responses: list[ProviderResponse]) -> None:
        self._responses = list(responses)
        self.requests = []

    async def generate(self, request):
        self.requests.append(request)
        if not self._responses:
            raise AssertionError("provider called more times than the journey declares")
        return self._responses.pop(0)


class _UnavailableRegistry:
    def require_active(self):
        raise ProviderUnavailableError("deterministic outage")


class _Registry:
    def __init__(self, provider) -> None:
        self.provider = provider

    def require_active(self):
        return self.provider


def _service(tmp_path, *, prefix: str = "golden") -> EngineExecutionService:
    return EngineExecutionService(
        SQLiteExecutionRepository(tmp_path / f"{prefix}-execution.sqlite3"),
        SQLiteEngineSubmissionStore(tmp_path / f"{prefix}-submission.sqlite3"),
        EngineAuthorityRegistry(
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
        ),
    )


def _command(
    *,
    execution_id: str,
    tool_definitions: tuple[ProviderToolDefinition, ...] = (),
    idempotency_key: str = "fixture",
    history: tuple[tuple[str, str], ...] | None = None,
) -> tuple[OperationEnvelope, EngineExecutionCommand]:
    started = _now()
    operation = OperationEnvelope(
        operation_id=str(uuid4()),
        tenant_id="tenant-a",
        actor_id="actor-a",
        capability="assistant.chat",
        created_at=started,
        deadline=started + timedelta(minutes=5),
        idempotency_key=idempotency_key,
        trace_id="trace:stage7:" + execution_id,
    )
    context_id = str(uuid4())
    turn_id = str(uuid4())
    policy_segment = str(uuid4())
    retrieval_seed = str(uuid4())
    source_snapshot = tuple(
        sorted(
            (
                (policy_segment, "a" * 64),
                (retrieval_seed, "b" * 64),
            )
        )
    )
    handoff = EngineContextHandoff(
        operation_id=operation.operation_id,
        execution_id=execution_id,
        turn_id=turn_id,
        tenant_id=operation.tenant_id,
        context_id=context_id,
        context_digest="c" * 64,
        compiler_version="stage7-fixture-compiler",
        source_snapshot=source_snapshot,
        data_class="internal",
        instructions="Use canonical authority and cite durable evidence.",
        prompt="Resolve the deterministic golden journey.",
        history=(
            history
            if history is not None
            else (
                ("user", "Earlier user turn."),
                ("assistant", "Earlier assistant turn."),
            )
        ),
        tools=tool_definitions,
    )
    allowed_tool_ids = [definition.tool_id for definition in tool_definitions]
    request = AIExecutionRequest(
        operation_id=operation.operation_id,
        execution_id=execution_id,
        objective="prove deterministic cross-plane AI execution",
        context_policy={
            "tenant_id": operation.tenant_id,
            "capability": operation.capability,
            "data_class": handoff.data_class,
            "context_id": handoff.context_id,
            "context_digest": handoff.context_digest,
            "compiler_version": handoff.compiler_version,
            "handoff_digest": handoff.handoff_digest,
            "source_snapshot": [
                [segment_id, digest]
                for segment_id, digest in handoff.source_snapshot
            ],
        },
        tool_policy={
            "tenant_id": operation.tenant_id,
            "allowed_tool_ids": allowed_tool_ids,
        },
        resource_budget={
            "max_model_turns": 4,
            "max_tool_calls": 4,
            "max_output_tokens": 1024,
        },
        stop_policy={
            "deadline": operation.deadline.isoformat(),
            "max_repeat_tool_batches": 1,
        },
        created_at=started,
    )
    authority = DelegatedAuthority(
        service_principal="codedock-backend",
        actor_id=operation.actor_id,
        tenant_id=operation.tenant_id,
        scopes=(
            "engine:submit",
            "engine:read",
            "engine:cancel",
            "engine:events",
            "engine:approve",
        ),
        capability=operation.capability,
        issued_at=started,
        expires_at=operation.deadline,
        request_binding=engine_request_binding(operation, request),
    )
    command = EngineExecutionCommand(
        operation=operation,
        execution_request=request,
        delegated_authority=authority,
        compiled_context=handoff,
        context_seed_refs=tuple(
            "context-segment:" + segment_id
            for segment_id, _ in source_snapshot
        ),
        resource_budget=dict(request.resource_budget),
        stream_preferences={"mode": "events"},
    )
    return operation, command


def _tool_response(
    *,
    tool_id: str,
    arguments: dict,
    call_id: str,
    response_id: str,
) -> ProviderResponse:
    return ProviderResponse(
        text=None,
        provider="deterministic",
        model="fixture-model",
        request_id=response_id,
        response_id=response_id,
        tool_calls=(
            ProviderToolCall(
                call_id=call_id,
                tool_id=tool_id,
                arguments=arguments,
            ),
        ),
        finish_reason=FinishReason.TOOL_CALLS,
        usage=ProviderUsage(
            input_tokens=7,
            output_tokens=3,
            total_tokens=10,
            usage_source="provider",
        ),
    )


def _tool_idempotency_key(
    execution_id: str,
    call_id: str,
    arguments: dict,
) -> str:
    return (
        execution_id
        + ":"
        + call_id
        + ":"
        + provider_arguments_digest(arguments)
    )


def _text_response(text: str, *, response_id: str) -> ProviderResponse:
    return ProviderResponse(
        text=text,
        provider="deterministic",
        model="fixture-model",
        request_id=response_id,
        response_id=response_id,
        finish_reason=FinishReason.COMPLETED,
        usage=ProviderUsage(
            input_tokens=11,
            output_tokens=5,
            total_tokens=16,
            usage_source="provider",
        ),
    )


async def _wait_result(
    service: EngineExecutionService,
    execution_id: str,
):
    for _ in range(1000):
        result = service.repository.result(execution_id)
        if result is not None:
            return result
        await asyncio.sleep(0)
    raise AssertionError("golden journey did not reach a durable result")


def _submit(
    service: EngineExecutionService,
    command: EngineExecutionCommand,
) -> None:
    service.submit(
        command,
        verified_service_principal="codedock-backend",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now(),
    )


def _events(
    service: EngineExecutionService,
    execution_id: str,
) -> tuple[dict, ...]:
    payload = service.events(
        execution_id,
        verified_service_principal="codedock-backend",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now(),
    )
    return tuple(payload["events"])


@pytest.mark.asyncio
async def test_stage7_prompt_only_journey_preserves_operation_context_and_terminal_lineage(
    tmp_path,
) -> None:
    provider = _SequenceProvider(
        [_text_response("prompt-only answer", response_id="provider-prompt-only")]
    )
    service = _service(tmp_path, prefix="prompt-only")
    operation, command = _command(
        execution_id="stage7-prompt-only",
        history=(),
    )
    _submit(service, command)

    coordinator = EngineExecutionCoordinator(
        service,
        provider_registry=_Registry(provider),
        tool_runtime=AsyncToolRuntime(),
        verification_hook=_verification,
    )
    await coordinator.ensure_started(command)
    result = await _wait_result(service, command.execution_request.execution_id)

    assert result.status == "completed"
    assert result.final_output == "prompt-only answer"
    assert result.provider_receipts == (
        "provider:deterministic:provider-prompt-only",
    )
    assert result.tool_receipts == ()
    assert result.verification_receipt["outcome"] == "passed"
    assert len(provider.requests) == 1
    request = provider.requests[0]
    assert request.operation_id == operation.operation_id
    assert request.execution_id == command.execution_request.execution_id
    assert request.history == ()
    assert request.context_id == command.compiled_context.context_id
    assert request.context_digest == command.compiled_context.context_digest

    terminal = [
        event
        for event in _events(service, command.execution_request.execution_id)
        if event["type"] == "execution.result"
    ]
    assert len(terminal) == 1
    assert terminal[0]["result"]["status"] == "completed"
    assert terminal[0]["result"]["provider_receipts"] == list(
        result.provider_receipts
    )

    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_stage7_multi_turn_journey_preserves_canonical_history_and_trace(
    tmp_path,
) -> None:
    history = (
        ("user", "First user turn."),
        ("assistant", "First assistant answer."),
        ("user", "Second user turn."),
    )
    provider = _SequenceProvider(
        [_text_response("second assistant answer", response_id="provider-multiturn")]
    )
    service = _service(tmp_path, prefix="multi-turn")
    operation, command = _command(
        execution_id="stage7-multi-turn",
        history=history,
    )
    _submit(service, command)

    coordinator = EngineExecutionCoordinator(
        service,
        provider_registry=_Registry(provider),
        tool_runtime=AsyncToolRuntime(),
        verification_hook=_verification,
    )
    await coordinator.ensure_started(command)
    result = await _wait_result(service, command.execution_request.execution_id)

    assert result.status == "completed"
    assert result.final_output == "second assistant answer"
    request = provider.requests[0]
    assert tuple((item.role, item.content) for item in request.history) == history
    assert request.operation_id == operation.operation_id
    assert request.execution_id == command.execution_request.execution_id
    # Provider turns have their own deterministic execution-turn identity.
    # The compiled context turn is an input lineage identity, not the provider
    # call's turn id; context identity/digest/snapshot bind that lineage.
    assert request.turn_id
    assert request.turn_id != command.compiled_context.turn_id
    assert request.context_id == command.compiled_context.context_id
    assert request.context_digest == command.compiled_context.context_digest
    assert request.context_source_snapshot == command.compiled_context.source_snapshot
    assert result.stream_terminal_event is not None

    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_stage7_approval_write_survives_restart_and_executes_effect_once(
    tmp_path,
) -> None:
    receipt_path = tmp_path / "stage7-approval-write-receipts.sqlite3"
    effects: list[str | None] = []
    manifest = ToolManifest(
        tool_id="repo.write",
        version="1.0.0",
        description="Write one deterministic repository target.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "minLength": 1, "maxLength": 256},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        effect=ToolEffect.REVERSIBLE,
        approval_required=True,
    )
    definition = ProviderToolDefinition(
        tool_id=manifest.tool_id,
        description=manifest.description,
        input_schema=dict(manifest.input_schema),
    )
    operation, command = _command(
        execution_id="stage7-approval-write",
        tool_definitions=(definition,),
        idempotency_key="approval-write",
    )
    service = _service(tmp_path, prefix="approval-write")
    _submit(service, command)

    first_tools = AsyncToolRuntime(
        receipt_store=SQLiteToolReceiptStore(receipt_path)
    )

    async def first_handler(request: ToolExecutionRequest) -> str:
        effects.append(request.approval_ref)
        return "artifact:approved-write"

    await first_tools.register(
        manifest,
        first_handler,
        postcondition=lambda _request, result_ref: result_ref == "artifact:approved-write",
    )
    first_provider = _SequenceProvider(
        [
            _tool_response(
                tool_id="repo.write",
                arguments={"path": "README.md"},
                call_id="call-write",
                response_id="provider-write-proposal",
            )
        ]
    )
    first = EngineExecutionCoordinator(
        service,
        provider_registry=_Registry(first_provider),
        tool_runtime=first_tools,
        verification_hook=_verification,
    )
    await first.ensure_started(command)

    for _ in range(200):
        current = service.repository.get(command.execution_request.execution_id)
        if current.state.value == "waiting_for_user":
            break
        await asyncio.sleep(0)
    else:
        raise AssertionError("approval journey did not suspend for user authority")

    pending = service.pending_tool_approvals(
        command.execution_request.execution_id,
        verified_service_principal="codedock-backend",
        actor_id=operation.actor_id,
        tenant_id=operation.tenant_id,
        now=_now(),
    )
    assert len(pending) == 1
    assert pending[0]["call_id"] == "call-write"
    assert pending[0]["tool_id"] == "repo.write"
    assert effects == []
    await first.shutdown()

    approval = service.approve_tool_call(
        command.execution_request.execution_id,
        verified_service_principal="codedock-backend",
        actor_id=operation.actor_id,
        tenant_id=operation.tenant_id,
        call_id=pending[0]["call_id"],
        tool_id=pending[0]["tool_id"],
        arguments_digest=pending[0]["arguments_digest"],
        idempotency_key=pending[0]["idempotency_key"],
        expires_at=min(
            operation.deadline,
            command.delegated_authority.expires_at,
        ) - timedelta(seconds=1),
        now=_now(),
    )

    restarted_tools = AsyncToolRuntime(
        receipt_store=SQLiteToolReceiptStore(receipt_path)
    )

    async def restarted_handler(request: ToolExecutionRequest) -> str:
        effects.append(request.approval_ref)
        return "artifact:approved-write"

    await restarted_tools.register(
        manifest,
        restarted_handler,
        postcondition=lambda _request, result_ref: result_ref == "artifact:approved-write",
    )
    final_provider = _SequenceProvider(
        [_text_response("write confirmed", response_id="provider-write-final")]
    )
    restarted = EngineExecutionCoordinator(
        service,
        provider_registry=_Registry(final_provider),
        tool_runtime=restarted_tools,
        verification_hook=_verification,
    )
    await restarted.ensure_execution(command.execution_request.execution_id)
    result = await _wait_result(service, command.execution_request.execution_id)

    assert result.status == "completed"
    assert result.final_output == "write confirmed"
    assert effects == [approval.approval_ref]
    assert result.usage["tool_calls"] == 1
    assert len(result.tool_receipts) == 1
    assert result.provider_receipts == (
        "provider:deterministic:provider-write-proposal",
        "provider:deterministic:provider-write-final",
    )
    assert result.verification_receipt["outcome"] == "passed"

    terminal = [
        event
        for event in _events(service, command.execution_request.execution_id)
        if event["type"] == "execution.result"
    ]
    assert len(terminal) == 1
    assert terminal[0]["result"]["tool_receipts"] == list(result.tool_receipts)

    await restarted.shutdown()
    restarted_tools.receipt_store.close()


@pytest.mark.asyncio
async def test_stage7_retrieval_tool_provider_journey_binds_durable_lineage(
    tmp_path,
) -> None:
    """One operation crosses retrieval, tool, provider, verify and stream planes."""

    planner = QueryPlanner()
    retrieval_calls: list[str] = []

    def fixture_retriever(query: str):
        retrieval_calls.append(query)
        return (
            ScoredResult(
                fragment_id="architecture-001",
                content="Canonical execution owns provider and tool authority.",
                score=1.0,
                plane="rag",
                provenance="fixture:stage7:architecture",
                metadata={"preview": "Canonical execution owns provider authority."},
            ),
            ScoredResult(
                fragment_id="recovery-001",
                content="Durable receipts fence retries after process loss.",
                score=0.8,
                plane="rag",
                provenance="fixture:stage7:recovery",
            ),
        )

    planner.register("fixture", fixture_retriever)
    pipeline = SearchPipeline(planner)

    receipt_path = tmp_path / "stage7-tool-receipts.sqlite3"
    receipt_store = SQLiteToolReceiptStore(receipt_path)
    tools = AsyncToolRuntime(receipt_store=receipt_store)
    retrieval_evidence: dict[str, object] = {}

    manifest = ToolManifest(
        tool_id="retrieval.search",
        version="1.0.0",
        description="Search the deterministic Stage-7 retrieval fixture.",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 256},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        effect=ToolEffect.READ_ONLY,
        approval_required=False,
    )

    async def retrieval_handler(request: ToolExecutionRequest) -> str:
        outcome = pipeline.search(
            str(request.arguments["query"]),
            top_k=2,
            render=True,
        )
        if not outcome.results:
            raise AssertionError("fixture retrieval unexpectedly returned no evidence")
        top = outcome.results[0]
        retrieval_evidence.update(
            {
                "query": outcome.query,
                "fragment_id": top.fragment_id,
                "provenance": top.provenance,
                "rendered": outcome.rendered,
            }
        )
        return "retrieval:" + top.fragment_id

    await tools.register(manifest, retrieval_handler)

    provider = _SequenceProvider(
        [
            _tool_response(
                tool_id="retrieval.search",
                arguments={"query": "canonical execution authority"},
                call_id="call-retrieval",
                response_id="provider-retrieval",
            ),
            _text_response(
                "Canonical execution retains authority and durable receipts preserve recovery.",
                response_id="provider-final",
            ),
        ]
    )
    service = _service(tmp_path, prefix="retrieval")
    tool_definition = ProviderToolDefinition(
        tool_id=manifest.tool_id,
        description=manifest.description,
        input_schema=dict(manifest.input_schema),
    )
    _, command = _command(
        execution_id="stage7-retrieval",
        tool_definitions=(tool_definition,),
    )
    _submit(service, command)

    coordinator = EngineExecutionCoordinator(
        service,
        provider_registry=_Registry(provider),
        tool_runtime=tools,
        verification_hook=_verification,
    )
    await coordinator.ensure_started(command)
    result = await _wait_result(service, command.execution_request.execution_id)

    assert result.status == "completed"
    assert result.final_output.startswith("Canonical execution")
    assert result.verification_receipt["outcome"] == "passed"
    assert result.evidence_refs == ("evidence:stage7-golden-journey",)
    assert result.provider_receipts == (
        "provider:deterministic:provider-retrieval",
        "provider:deterministic:provider-final",
    )
    assert len(result.tool_receipts) == 1
    assert retrieval_calls == ["canonical execution authority"]
    assert retrieval_evidence["fragment_id"] == "architecture-001"
    assert retrieval_evidence["provenance"] == "fixture:stage7:architecture"
    assert "Canonical" in str(retrieval_evidence["rendered"])

    assert len(provider.requests) == 2
    for request in provider.requests:
        assert request.operation_id == command.operation.operation_id
        assert request.execution_id == command.execution_request.execution_id
        assert request.context_id == command.compiled_context.context_id
        assert request.context_digest == command.compiled_context.context_digest
        assert (
            request.context_source_snapshot
            == command.compiled_context.source_snapshot
        )

    durable = receipt_store.get(
        tenant_id=command.operation.tenant_id,
        operation_id=command.operation.operation_id,
        idempotency_key=_tool_idempotency_key(
            command.execution_request.execution_id,
            "call-retrieval",
            {"query": "canonical execution authority"},
        ),
    )
    assert durable is not None
    assert durable.status == "committed"
    assert durable.receipt is not None
    assert durable.receipt.status is ToolExecutionStatus.SUCCEEDED
    assert durable.receipt.result_ref == "retrieval:architecture-001"

    events = _events(service, command.execution_request.execution_id)
    terminal = [event for event in events if event["type"] == "execution.result"]
    assert len(terminal) == 1
    assert terminal[0]["result"]["operation_id"] == command.operation.operation_id
    assert terminal[0]["result"]["tool_receipts"] == list(result.tool_receipts)
    assert terminal[0]["result"]["provider_receipts"] == list(
        result.provider_receipts
    )
    assert result.stream_terminal_event is not None

    await coordinator.shutdown()
    receipt_store.close()


@pytest.mark.asyncio
async def test_stage7_artifact_action_is_receipted_once(
    tmp_path,
) -> None:
    """Artifact production is a governed side effect with durable idempotency."""

    effects: list[str] = []
    receipt_path = tmp_path / "stage7-artifact-receipts.sqlite3"
    receipt_store = SQLiteToolReceiptStore(receipt_path)
    tools = AsyncToolRuntime(receipt_store=receipt_store)

    manifest = ToolManifest(
        tool_id="artifact.package",
        version="1.0.0",
        description="Create one deterministic release artifact.",
        input_schema={
            "type": "object",
            "properties": {
                "build_id": {"type": "string", "minLength": 1, "maxLength": 128},
            },
            "required": ["build_id"],
            "additionalProperties": False,
        },
        effect=ToolEffect.REVERSIBLE,
        approval_required=False,
    )

    async def package(request: ToolExecutionRequest) -> str:
        build_id = str(request.arguments["build_id"])
        effects.append(build_id)
        return "artifact:" + build_id

    await tools.register(
        manifest,
        package,
        postcondition=lambda _request, result_ref: result_ref == "artifact:golden-build",
    )

    provider = _SequenceProvider(
        [
            _tool_response(
                tool_id="artifact.package",
                arguments={"build_id": "golden-build"},
                call_id="call-artifact",
                response_id="provider-artifact",
            ),
            _text_response(
                "Artifact golden-build is ready.",
                response_id="provider-artifact-final",
            ),
        ]
    )
    service = _service(tmp_path, prefix="artifact")
    tool_definition = ProviderToolDefinition(
        tool_id=manifest.tool_id,
        description=manifest.description,
        input_schema=dict(manifest.input_schema),
    )
    _, command = _command(
        execution_id="stage7-artifact",
        tool_definitions=(tool_definition,),
        idempotency_key="fixture",
    )
    _submit(service, command)

    coordinator = EngineExecutionCoordinator(
        service,
        provider_registry=_Registry(provider),
        tool_runtime=tools,
        verification_hook=_verification,
    )
    await coordinator.ensure_started(command)
    result = await _wait_result(service, command.execution_request.execution_id)

    assert result.status == "completed"
    assert result.final_output == "Artifact golden-build is ready."
    assert effects == ["golden-build"]
    assert len(result.tool_receipts) == 1

    durable = receipt_store.get(
        tenant_id=command.operation.tenant_id,
        operation_id=command.operation.operation_id,
        idempotency_key=_tool_idempotency_key(
            command.execution_request.execution_id,
            "call-artifact",
            {"build_id": "golden-build"},
        ),
    )
    assert durable is not None
    assert durable.status == "committed"
    assert durable.receipt is not None
    assert durable.receipt.result_ref == "artifact:golden-build"

    await coordinator.shutdown()
    receipt_store.close()


@pytest.mark.asyncio
async def test_stage7_expired_approval_can_be_renewed_without_widening_identity(
    tmp_path,
) -> None:
    """Expired approval can be renewed for the exact pending call only."""

    receipt_path = tmp_path / "stage7-approval-renewal-receipts.sqlite3"
    effects: list[str | None] = []
    manifest = ToolManifest(
        tool_id="repo.write",
        version="1.0.0",
        description="Write one deterministic repository target.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "minLength": 1, "maxLength": 256},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        effect=ToolEffect.REVERSIBLE,
        approval_required=True,
    )
    definition = ProviderToolDefinition(
        tool_id=manifest.tool_id,
        description=manifest.description,
        input_schema=dict(manifest.input_schema),
    )
    operation, command = _command(
        execution_id="stage7-approval-renewal",
        tool_definitions=(definition,),
        idempotency_key="approval-renewal",
    )
    service = _service(tmp_path, prefix="approval-renewal")
    _submit(service, command)

    first_tools = AsyncToolRuntime(
        receipt_store=SQLiteToolReceiptStore(receipt_path)
    )

    async def handler(request: ToolExecutionRequest) -> str:
        effects.append(request.approval_ref)
        return "artifact:renewed-write"

    await first_tools.register(
        manifest,
        handler,
        postcondition=lambda _request, result_ref: result_ref == "artifact:renewed-write",
    )
    first_provider = _SequenceProvider(
        [
            _tool_response(
                tool_id="repo.write",
                arguments={"path": "README.md"},
                call_id="call-renew",
                response_id="provider-renew-proposal",
            )
        ]
    )
    first = EngineExecutionCoordinator(
        service,
        provider_registry=_Registry(first_provider),
        tool_runtime=first_tools,
        verification_hook=_verification,
    )
    await first.ensure_started(command)

    for _ in range(200):
        current = service.repository.get(command.execution_request.execution_id)
        if current.state.value == "waiting_for_user":
            break
        await asyncio.sleep(0)
    else:
        raise AssertionError("renewal journey did not suspend for approval")

    pending = service.pending_tool_approvals(
        command.execution_request.execution_id,
        verified_service_principal="codedock-backend",
        actor_id=operation.actor_id,
        tenant_id=operation.tenant_id,
        now=_now(),
    )
    assert len(pending) == 1
    await first.shutdown()

    issued = _now()
    initial = service.approve_tool_call(
        command.execution_request.execution_id,
        verified_service_principal="codedock-backend",
        actor_id=operation.actor_id,
        tenant_id=operation.tenant_id,
        call_id=pending[0]["call_id"],
        tool_id=pending[0]["tool_id"],
        arguments_digest=pending[0]["arguments_digest"],
        idempotency_key=pending[0]["idempotency_key"],
        expires_at=issued + timedelta(seconds=1),
        now=issued,
    )
    assert service.active_approval_refs(
        command.execution_request.execution_id,
        now=issued,
    ) == {pending[0]["call_id"]: initial.approval_ref}
    assert service.active_approval_refs(
        command.execution_request.execution_id,
        now=issued + timedelta(seconds=2),
    ) == {}

    renewed = service.approve_tool_call(
        command.execution_request.execution_id,
        verified_service_principal="codedock-backend",
        actor_id=operation.actor_id,
        tenant_id=operation.tenant_id,
        call_id=pending[0]["call_id"],
        tool_id=pending[0]["tool_id"],
        arguments_digest=pending[0]["arguments_digest"],
        idempotency_key=pending[0]["idempotency_key"],
        expires_at=min(
            operation.deadline,
            issued + timedelta(minutes=1),
        ),
        now=issued + timedelta(seconds=2),
    )
    assert renewed.approval_id == initial.approval_id
    assert renewed.approval_ref == initial.approval_ref
    assert renewed.expires_at > initial.expires_at

    with pytest.raises(
        EngineSubmissionConflict,
        match="active approval cannot be widened",
    ):
        service.submissions.remember_approval(
            type(renewed)(
                approval_id=renewed.approval_id,
                execution_id=renewed.execution_id,
                call_id=renewed.call_id,
                tool_id=renewed.tool_id,
                arguments_digest=renewed.arguments_digest,
                actor_id=renewed.actor_id,
                tenant_id=renewed.tenant_id,
                idempotency_key=renewed.idempotency_key,
                bound_approval_ref=renewed.bound_approval_ref,
                issued_at=renewed.issued_at + timedelta(seconds=1),
                expires_at=renewed.expires_at + timedelta(seconds=1),
            )
        )

    restarted_tools = AsyncToolRuntime(
        receipt_store=SQLiteToolReceiptStore(receipt_path)
    )
    await restarted_tools.register(
        manifest,
        handler,
        postcondition=lambda _request, result_ref: result_ref == "artifact:renewed-write",
    )
    final_provider = _SequenceProvider(
        [_text_response("renewed write confirmed", response_id="provider-renew-final")]
    )
    restarted = EngineExecutionCoordinator(
        service,
        provider_registry=_Registry(final_provider),
        tool_runtime=restarted_tools,
        verification_hook=_verification,
    )
    await restarted.ensure_execution(command.execution_request.execution_id)
    result = await _wait_result(service, command.execution_request.execution_id)

    assert result.status == "completed"
    assert result.final_output == "renewed write confirmed"
    assert effects == [renewed.approval_ref]
    assert result.usage["tool_calls"] == 1
    assert len(result.tool_receipts) == 1
    await restarted.shutdown()
    restarted_tools.receipt_store.close()


@pytest.mark.asyncio
async def test_stage7_governance_export_delete_spans_artifact_and_retrieval_planes(
    tmp_path,
) -> None:
    """One tenant lifecycle request exports and deletes across canonical planes."""

    state = ServerState()
    try:
        artifacts = state.bind_canonical_artifact_store(
            tmp_path / "stage7-governed-artifacts"
        )
        retrieval = state.bind_canonical_retrieval_index()
        assert state.governance_lifecycle_executor is not None

        artifact = artifacts.write_bytes(
            tenant_id="tenant-a",
            artifact_id="stage7-report.bin",
            payload=b"stage7-governed-artifact",
            data_class="confidential",
            purposes=("artifact-delivery", "model-inference"),
            created_at=10.0,
            retention_until=100.0,
        )
        document = retrieval.add(
            tenant_id="tenant-a",
            doc_id="stage7-retrieval-doc",
            text="stage7 governed retrieval evidence",
            created_at=10.0,
        )

        inventory = state.governance_registry.export_inventory("tenant-a")
        inventory_ids = {
            item["record_id"] for item in inventory["records"]
        }
        assert artifact.record_id in inventory_ids
        assert document.record_id in inventory_ids

        exported = await state.governance_lifecycle_executor.export_tenant(
            "tenant-a"
        )
        exported_ids = {
            item["governance"]["record_id"]
            for item in exported.records
        }
        assert artifact.record_id in exported_ids
        assert document.record_id in exported_ids
        artifact_export = next(
            item
            for item in exported.records
            if item["governance"]["record_id"] == artifact.record_id
        )
        retrieval_export = next(
            item
            for item in exported.records
            if item["governance"]["record_id"] == document.record_id
        )
        assert artifact_export["payload"]["artifact_id"] == "stage7-report.bin"
        assert retrieval_export["payload"]["doc_id"] == "stage7-retrieval-doc"

        plan = state.governance_lifecycle.request_deletion(
            "tenant-a",
            record_ids=(artifact.record_id, document.record_id),
            now=20.0,
        )
        deletion = (
            await state.governance_lifecycle_executor.execute_deletion_plan(
                plan,
                now=21.0,
            )
        )
        assert {receipt.record_id for receipt in deletion.receipts} == {
            artifact.record_id,
            document.record_id,
        }
        assert artifacts.read_bytes(
            "tenant-a",
            "stage7-report.bin",
        ) is None
        assert retrieval.size("tenant-a") == 0
        assert (
            state.governance_lifecycle.get(artifact.record_id)["state"]
            == "deleted"
        )
        assert (
            state.governance_lifecycle.get(document.record_id)["state"]
            == "deleted"
        )
    finally:
        state.close_governance_registry()


@pytest.mark.asyncio
async def test_stage7_provider_outage_is_durable_degraded_result_without_tool_io(
    tmp_path,
) -> None:
    """Provider loss fails closed into durable state and never invokes a tool."""

    service = _service(tmp_path, prefix="outage")
    _, command = _command(
        execution_id="stage7-provider-outage",
        idempotency_key="fixture",
    )
    _submit(service, command)

    coordinator = EngineExecutionCoordinator(
        service,
        provider_registry=_UnavailableRegistry(),
        tool_runtime=AsyncToolRuntime(),
        verification_hook=_verification,
    )
    await coordinator.ensure_started(command)
    result = await _wait_result(service, command.execution_request.execution_id)

    assert result.status == "failed"
    assert result.final_output is None
    assert result.usage["error_code"] == "provider_unavailable"
    assert result.tool_receipts == ()

    terminal = [
        event
        for event in _events(service, command.execution_request.execution_id)
        if event["type"] == "execution.result"
    ]
    assert len(terminal) == 1
    assert terminal[0]["result"]["status"] == "failed"

    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_stage7_cancel_race_fences_late_provider_success(
    tmp_path,
) -> None:
    """Cancellation wins over a provider response that arrives after the fence."""

    started = asyncio.Event()
    release = asyncio.Event()

    class GateProvider:
        provider_id = "deterministic"
        model = "fixture-model"
        available = True

        async def generate(self, _request):
            started.set()
            await release.wait()
            return _text_response(
                "late success must never become canonical output",
                response_id="provider-late",
            )

    service = _service(tmp_path, prefix="cancel")
    operation, command = _command(
        execution_id="stage7-cancel-race",
        idempotency_key="fixture",
    )
    _submit(service, command)

    coordinator = EngineExecutionCoordinator(
        service,
        provider_registry=_Registry(GateProvider()),
        tool_runtime=AsyncToolRuntime(),
        verification_hook=_verification,
    )
    await coordinator.ensure_started(command)
    await asyncio.wait_for(started.wait(), timeout=2)

    cancellation = service.cancel(
        command.execution_request.execution_id,
        verified_service_principal="codedock-backend",
        actor_id=operation.actor_id,
        tenant_id=operation.tenant_id,
        now=_now(),
    )
    assert cancellation.cancellation_requested is True

    release.set()
    result = await _wait_result(service, command.execution_request.execution_id)

    assert result.status == "cancelled"
    assert result.final_output is None
    assert result.usage["error_code"] == "cancellation_requested"
    assert result.provider_receipts == (
        "provider:deterministic:provider-late",
    )

    checkpoint = service.repository.latest_checkpoint(
        command.execution_request.execution_id
    )
    assert checkpoint is not None
    assert checkpoint.payload["last_provider"]["late_result_fenced"] is True

    terminal = [
        event
        for event in _events(service, command.execution_request.execution_id)
        if event["type"] == "execution.result"
    ]
    assert len(terminal) == 1
    assert terminal[0]["result"]["status"] == "cancelled"

    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_stage7_restart_ambiguity_never_replays_uncommitted_tool_effect(
    tmp_path,
) -> None:
    """A crash after durable reservation but before commit stays in-doubt."""

    receipt_path = tmp_path / "stage7-in-doubt.sqlite3"
    operation_id = str(uuid4())
    request = ToolExecutionRequest(
        request_id=str(uuid4()),
        operation_id=operation_id,
        tenant_id="tenant-a",
        tool_id="artifact.package",
        idempotency_key="dummy",
        arguments={"build_id": "ambiguous-build"},
        requested_at=_now(),
    )

    before_crash = SQLiteToolReceiptStore(receipt_path)
    reservation = before_crash.reserve(request, now=_now())
    assert reservation.status == "owner"
    before_crash.close()

    effects: list[str] = []
    after_restart = SQLiteToolReceiptStore(receipt_path)
    runtime = AsyncToolRuntime(receipt_store=after_restart)
    manifest = ToolManifest(
        tool_id="artifact.package",
        version="1.0.0",
        description="Create one deterministic release artifact.",
        input_schema={
            "type": "object",
            "properties": {
                "build_id": {"type": "string", "minLength": 1, "maxLength": 128},
            },
            "required": ["build_id"],
            "additionalProperties": False,
        },
        effect=ToolEffect.REVERSIBLE,
        approval_required=False,
    )

    async def package(retry: ToolExecutionRequest) -> str:
        effects.append(str(retry.arguments["build_id"]))
        return "artifact:" + str(retry.arguments["build_id"])

    await runtime.register(manifest, package)
    receipt = await runtime.execute(request, now=_now())

    assert receipt.status is ToolExecutionStatus.DENIED
    assert receipt.error_code == "execution_in_doubt"
    assert receipt.metered_tool_calls == 0
    assert effects == []

    durable = after_restart.get(
        tenant_id="tenant-a",
        operation_id=operation_id,
        idempotency_key="dummy",
    )
    assert durable is not None
    assert durable.status == "in_doubt"
    after_restart.close()
