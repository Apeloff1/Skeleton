from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
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
    SQLiteEngineSubmissionStore,
)
from skeleton.contracts.ai_execution import AIExecutionRequest
from skeleton.contracts.operation import OperationEnvelope
from skeleton.intelligence.admission_runtime import AdmissionRuntime
from skeleton.intelligence.execution_runtime import ExecutionVerificationDecision
from skeleton.intelligence.quota import TenantQuota, TenantQuotaLedger
from skeleton.persistence.execution_repository import SQLiteExecutionRepository
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


def _now() -> datetime:
    return datetime(2026, 9, 23, 20, 30, tzinfo=timezone.utc)


def _verified_execution(
    _request: AIExecutionRequest,
    candidate: str,
    context_digest: str,
) -> ExecutionVerificationDecision:
    return ExecutionVerificationDecision(
        passed=True,
        receipt={
            "outcome": "passed",
            "policy_satisfied": True,
            "verifier_id": "test:engine-coordinator",
            "candidate_digest": hashlib.sha256(
                candidate.encode("utf-8")
            ).hexdigest(),
            "context_digest": context_digest,
        },
        evidence_refs=("evidence:test-engine-coordinator",),
    )


class FakeProvider:
    provider_id = "fake"
    model = "fake-model"
    available = True

    def __init__(self, *, text: str = "engine answer", gate=None) -> None:
        self.text = text
        self.requests = []
        self.gate = gate

    async def generate(self, request):
        self.requests.append(request)
        if self.gate is not None:
            await self.gate.wait()
        return ProviderResponse(
            text=self.text,
            provider=self.provider_id,
            model=self.model,
            request_id="provider-1",
            response_id="provider-1",
            finish_reason=FinishReason.COMPLETED,
            usage=ProviderUsage(
                input_tokens=10,
                output_tokens=5,
                total_tokens=15,
                usage_source="provider",
            ),
            context_id=request.context_id,
            context_digest=request.context_digest,
            context_source_snapshot=request.context_source_snapshot,
            context_compiler_version=request.context_compiler_version,
        )


class FakeRegistry:
    def __init__(self, provider=None, *, unavailable: bool = False) -> None:
        self.provider = provider
        self.unavailable = unavailable

    def require_active(self):
        if self.unavailable:
            from skeleton.provider_runtime import ProviderUnavailableError

            raise ProviderUnavailableError("not configured")
        return self.provider


def _bundle(*, execution_id: str = "exec-golden"):
    runtime_deadline = datetime.now(timezone.utc) + timedelta(minutes=10)
    operation = OperationEnvelope(
        operation_id=str(uuid4()),
        tenant_id="tenant-a",
        actor_id="actor-a",
        capability="assistant.chat",
        created_at=_now(),
        deadline=runtime_deadline,
        idempotency_key="golden-idem",
        trace_id="trace-golden",
    )
    context_id = str(uuid4())
    turn_id = str(uuid4())
    segment_a = str(uuid4())
    segment_b = str(uuid4())
    snapshot = tuple(
        sorted(
            (
                (segment_a, "a" * 64),
                (segment_b, "b" * 64),
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
        compiler_version="test-compiler",
        source_snapshot=snapshot,
        data_class="internal",
        instructions="Follow the canonical policy.",
        prompt="new question",
        history=(
            ("user", "older question"),
            ("assistant", "older answer"),
        ),
    )
    request = AIExecutionRequest(
        operation_id=operation.operation_id,
        execution_id=execution_id,
        objective="new question",
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
            "allowed_tool_ids": [],
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
        created_at=_now(),
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
        issued_at=_now(),
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
            for segment_id, _ in snapshot
        ),
        resource_budget=dict(request.resource_budget),
        stream_preferences={"mode": "events"},
    )
    return operation, command


def _service(tmp_path):
    repo = SQLiteExecutionRepository(tmp_path / "execution.sqlite3")
    submissions = SQLiteEngineSubmissionStore(
        tmp_path / "submissions.sqlite3"
    )
    registry = EngineAuthorityRegistry(
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
    return EngineExecutionService(repo, submissions, registry)



def _admitted_service(tmp_path):
    repo = SQLiteExecutionRepository(
        tmp_path / "execution-admitted.sqlite3"
    )
    submissions = SQLiteEngineSubmissionStore(
        tmp_path / "submissions-admitted.sqlite3"
    )
    registry = EngineAuthorityRegistry(
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
    ledger = TenantQuotaLedger()
    runtime = AdmissionRuntime(
        quota_ledger=ledger,
        default_tenant_quota=TenantQuota(
            window_id="engine-coordinator-test",
            max_operations=100,
            max_input_tokens=1_000_000,
            max_output_tokens=1_000_000,
            max_cost_usd=100.0,
            max_tool_calls=1_000,
            max_artifact_bytes=10_000_000,
            max_storage_bytes=10_000_000,
            max_concurrent_operations=16,
        ),
    )
    return (
        EngineExecutionService(
            repo,
            submissions,
            registry,
            admission_runtime=runtime,
        ),
        runtime,
        ledger,
    )


async def _wait_result(service, execution_id: str):
    for _ in range(100):
        result = service.repository.result(execution_id)
        if result is not None:
            return result
        await asyncio.sleep(0)
    raise AssertionError("engine execution did not complete")


@pytest.mark.asyncio
async def test_coordinator_golden_trace_preserves_compiled_context_lineage(
    tmp_path,
) -> None:
    service = _service(tmp_path)
    operation, command = _bundle()
    service.submit(
        command,
        verified_service_principal="codedock-backend",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now(),
    )
    provider = FakeProvider()
    coordinator = EngineExecutionCoordinator(
        service,
        provider_registry=FakeRegistry(provider),
        tool_runtime=AsyncToolRuntime(),
        verification_hook=_verified_execution,
    )

    await coordinator.ensure_started(command)
    result = await _wait_result(service, command.execution_request.execution_id)

    assert result.status == "completed"
    assert result.final_output == "engine answer"
    assert result.verification_receipt["outcome"] == "passed"
    assert len(provider.requests) == 1
    request = provider.requests[0]
    assert request.instructions == "Follow the canonical policy."
    assert request.prompt == "new question"
    assert [(item.role, item.content) for item in request.history] == [
        ("user", "older question"),
        ("assistant", "older answer"),
    ]
    assert request.operation_id == operation.operation_id
    assert request.execution_id == command.execution_request.execution_id
    assert request.context_id == command.compiled_context.context_id
    assert request.context_digest == command.compiled_context.context_digest
    assert (
        request.context_source_snapshot
        == command.compiled_context.source_snapshot
    )
    assert (
        request.context_compiler_version
        == command.compiled_context.compiler_version
    )

    status = service.status(
        command.execution_request.execution_id,
        verified_service_principal="codedock-backend",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now(),
    )
    assert status.operation_state == "completed"
    events = service.events(
        command.execution_request.execution_id,
        verified_service_principal="codedock-backend",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now(),
    )
    assert any(event["type"] == "execution.result" for event in events["events"])
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_coordinator_duplicate_launch_runs_one_provider_turn(tmp_path) -> None:
    service = _service(tmp_path)
    _, command = _bundle()
    service.submit(
        command,
        verified_service_principal="codedock-backend",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now(),
    )
    gate = asyncio.Event()
    provider = FakeProvider(gate=gate)
    coordinator = EngineExecutionCoordinator(
        service,
        provider_registry=FakeRegistry(provider),
        tool_runtime=AsyncToolRuntime(),
        verification_hook=_verified_execution,
    )

    await coordinator.ensure_started(command)
    await coordinator.ensure_started(command)
    await asyncio.sleep(0)
    assert len(provider.requests) == 1

    gate.set()
    await _wait_result(service, command.execution_request.execution_id)
    assert len(provider.requests) == 1
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_coordinator_fences_late_provider_result_after_cancel(tmp_path) -> None:
    service = _service(tmp_path)
    _, command = _bundle(execution_id="exec-cancel-race")
    service.submit(
        command,
        verified_service_principal="codedock-backend",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now(),
    )

    gate = asyncio.Event()
    provider = FakeProvider(text="must never become visible success", gate=gate)
    coordinator = EngineExecutionCoordinator(
        service,
        provider_registry=FakeRegistry(provider),
        tool_runtime=AsyncToolRuntime(),
        verification_hook=_verified_execution,
    )

    await coordinator.ensure_started(command)
    for _ in range(100):
        if provider.requests:
            break
        await asyncio.sleep(0)
    else:
        raise AssertionError("provider request did not start")

    cancelled = service.cancel(
        command.execution_request.execution_id,
        verified_service_principal="codedock-backend",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now(),
    )
    assert cancelled.cancellation_requested is True

    gate.set()
    result = await _wait_result(
        service,
        command.execution_request.execution_id,
    )

    assert result.status == "cancelled"
    assert result.final_output is None
    assert result.usage["error_code"] == "cancellation_requested"
    assert len(provider.requests) == 1
    assert result.provider_receipts

    checkpoint = service.repository.latest_checkpoint(
        command.execution_request.execution_id
    )
    assert checkpoint is not None
    last_provider = checkpoint.payload["last_provider"]
    assert last_provider["late_result_fenced"] is True
    assert last_provider["text"] == "must never become visible success"

    status = service.status(
        command.execution_request.execution_id,
        verified_service_principal="codedock-backend",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now(),
    )
    assert status.execution_state == "cancelled"
    assert status.failure_code == "cancellation_requested"

    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_coordinator_fences_late_provider_result_after_cancel(tmp_path) -> None:
    service = _service(tmp_path)
    _, command = _bundle(execution_id="exec-cancel-race")
    service.submit(
        command,
        verified_service_principal="codedock-backend",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now(),
    )

    gate = asyncio.Event()
    provider = FakeProvider(text="must never become visible success", gate=gate)
    coordinator = EngineExecutionCoordinator(
        service,
        provider_registry=FakeRegistry(provider),
        tool_runtime=AsyncToolRuntime(),
        verification_hook=_verified_execution,
    )

    await coordinator.ensure_started(command)
    for _ in range(100):
        if provider.requests:
            break
        await asyncio.sleep(0)
    else:
        raise AssertionError("provider request did not start")

    cancelled = service.cancel(
        command.execution_request.execution_id,
        verified_service_principal="codedock-backend",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now(),
    )
    assert cancelled.cancellation_requested is True

    gate.set()
    result = await _wait_result(
        service,
        command.execution_request.execution_id,
    )

    assert result.status == "cancelled"
    assert result.final_output is None
    assert result.usage["error_code"] == "cancellation_requested"
    assert len(provider.requests) == 1
    assert result.provider_receipts

    checkpoint = service.repository.latest_checkpoint(
        command.execution_request.execution_id
    )
    assert checkpoint is not None
    last_provider = checkpoint.payload["last_provider"]
    assert last_provider["late_result_fenced"] is True
    assert last_provider["text"] == "must never become visible success"

    status = service.status(
        command.execution_request.execution_id,
        verified_service_principal="codedock-backend",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now(),
    )
    assert status.execution_state == "cancelled"
    assert status.failure_code == "cancellation_requested"

    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_coordinator_restart_recovery_uses_durable_submission(tmp_path) -> None:
    service = _service(tmp_path)
    _, command = _bundle()
    service.submit(
        command,
        verified_service_principal="codedock-backend",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now(),
    )

    provider = FakeProvider(text="recovered")
    recovered = EngineExecutionCoordinator(
        service,
        provider_registry=FakeRegistry(provider),
        tool_runtime=AsyncToolRuntime(),
        verification_hook=_verified_execution,
    )
    recovered_ids = await recovered.recover()
    result = await _wait_result(service, command.execution_request.execution_id)

    assert recovered_ids == (command.execution_request.execution_id,)
    assert result.final_output == "recovered"
    assert len(provider.requests) == 1
    await recovered.shutdown()


@pytest.mark.asyncio
async def test_coordinator_provider_unavailable_becomes_durable_failure(
    tmp_path,
) -> None:
    service = _service(tmp_path)
    _, command = _bundle()
    service.submit(
        command,
        verified_service_principal="codedock-backend",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now(),
    )
    coordinator = EngineExecutionCoordinator(
        service,
        provider_registry=FakeRegistry(unavailable=True),
        tool_runtime=AsyncToolRuntime(),
        verification_hook=_verified_execution,
    )

    await coordinator.ensure_started(command)
    result = await _wait_result(service, command.execution_request.execution_id)

    assert result.status == "failed"
    assert result.usage["error_code"] == "provider_unavailable"
    await coordinator.shutdown()



class SequenceProvider:
    provider_id = "fake"
    model = "fake-model"
    available = True

    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.requests = []

    async def generate(self, request):
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("provider called more times than expected")
        return self.responses.pop(0)


def _approval_tool_response(call_id: str) -> ProviderResponse:
    return ProviderResponse(
        text=None,
        provider="fake",
        model="fake-model",
        request_id="provider-tool",
        response_id="provider-tool",
        tool_calls=(
            ProviderToolCall(
                call_id=call_id,
                tool_id="repo.write",
                arguments={"path": "README.md"},
            ),
        ),
        finish_reason=FinishReason.TOOL_CALLS,
        usage=ProviderUsage(
            input_tokens=10,
            output_tokens=3,
            total_tokens=13,
            usage_source="provider",
        ),
    )


def _approval_tool_manifest() -> ToolManifest:
    return ToolManifest(
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


@pytest.mark.asyncio
async def test_coordinator_durable_approval_resumes_effect_once_after_restart(
    tmp_path,
) -> None:
    service = _service(tmp_path)
    operation, base = _bundle(execution_id="exec-approval")
    handoff = EngineContextHandoff(
        operation_id=base.compiled_context.operation_id,
        execution_id=base.compiled_context.execution_id,
        turn_id=base.compiled_context.turn_id,
        tenant_id=base.compiled_context.tenant_id,
        context_id=base.compiled_context.context_id,
        context_digest=base.compiled_context.context_digest,
        compiler_version=base.compiled_context.compiler_version,
        source_snapshot=base.compiled_context.source_snapshot,
        data_class=base.compiled_context.data_class,
        instructions=base.compiled_context.instructions,
        prompt=base.compiled_context.prompt,
        history=base.compiled_context.history,
        tools=(
            ProviderToolDefinition(
                tool_id="repo.write",
                description="Write one repository file.",
                input_schema={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                    "additionalProperties": False,
                },
            ),
        ),
    )
    approval_context_policy = dict(base.execution_request.context_policy)
    approval_context_policy["handoff_digest"] = handoff.handoff_digest
    request = AIExecutionRequest(
        operation_id=base.execution_request.operation_id,
        execution_id=base.execution_request.execution_id,
        objective=base.execution_request.objective,
        context_policy=approval_context_policy,
        tool_policy={
            "tenant_id": operation.tenant_id,
            "allowed_tool_ids": ["repo.write"],
        },
        resource_budget=dict(base.execution_request.resource_budget),
        stop_policy=dict(base.execution_request.stop_policy),
        created_at=base.execution_request.created_at,
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
        issued_at=_now(),
        expires_at=operation.deadline,
        request_binding=engine_request_binding(operation, request),
    )
    command = EngineExecutionCommand(
        operation=operation,
        execution_request=request,
        delegated_authority=authority,
        compiled_context=handoff,
        context_seed_refs=base.context_seed_refs,
        resource_budget=dict(request.resource_budget),
        stream_preferences={"mode": "events"},
    )
    service.submit(
        command,
        verified_service_principal="codedock-backend",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now(),
    )

    receipt_path = tmp_path / "tool-receipts.sqlite3"
    effects: list[str | None] = []
    tools = AsyncToolRuntime(
        receipt_store=SQLiteToolReceiptStore(receipt_path)
    )

    async def handler(tool_request):
        effects.append(tool_request.approval_ref)
        return "artifact:approved-write"

    await tools.register(_approval_tool_manifest(), handler)
    first_provider = SequenceProvider([_approval_tool_response("call-write")])
    coordinator = EngineExecutionCoordinator(
        service,
        provider_registry=FakeRegistry(first_provider),
        tool_runtime=tools,
        verification_hook=_verified_execution,
    )

    await coordinator.ensure_started(command)
    for _ in range(100):
        current = service.repository.get("exec-approval")
        if current.state.value == "waiting_for_user":
            break
        await asyncio.sleep(0)
    else:
        raise AssertionError("execution did not suspend for approval")

    pending = service.pending_tool_approvals(
        "exec-approval",
        verified_service_principal="codedock-backend",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now(),
    )
    assert len(pending) == 1
    assert pending[0]["call_id"] == "call-write"
    assert effects == []
    await coordinator.shutdown()

    approval = service.approve_tool_call(
        "exec-approval",
        verified_service_principal="codedock-backend",
        actor_id="actor-a",
        tenant_id="tenant-a",
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

    async def restarted_handler(tool_request):
        effects.append(tool_request.approval_ref)
        return "artifact:approved-write"

    await restarted_tools.register(
        _approval_tool_manifest(),
        restarted_handler,
    )
    final_provider = SequenceProvider(
        [
            ProviderResponse(
                text="write confirmed",
                provider="fake",
                model="fake-model",
                request_id="provider-final",
                response_id="provider-final",
                finish_reason=FinishReason.COMPLETED,
                usage=ProviderUsage(
                    input_tokens=8,
                    output_tokens=4,
                    total_tokens=12,
                    usage_source="provider",
                ),
            )
        ]
    )
    restarted = EngineExecutionCoordinator(
        service,
        provider_registry=FakeRegistry(final_provider),
        tool_runtime=restarted_tools,
        verification_hook=_verified_execution,
    )

    await restarted.ensure_execution("exec-approval")
    result = await _wait_result(service, "exec-approval")

    assert result.status == "completed"
    assert result.final_output == "write confirmed"
    assert result.verification_receipt["outcome"] == "passed"
    assert effects == [approval.approval_ref]
    assert result.usage["tool_calls"] == 1
    assert len(result.tool_receipts) == 1
    assert final_provider.requests
    await restarted.shutdown()

@pytest.mark.asyncio
async def test_coordinator_completes_execution_admission_at_terminal_state(
    tmp_path,
) -> None:
    service, runtime, ledger = _admitted_service(tmp_path)
    _, command = _bundle(execution_id="exec-admitted-terminal")
    service.submit(
        command,
        verified_service_principal="codedock-backend",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now(),
    )
    assert ledger.snapshot("tenant-a")["active_reservations"] == 1

    coordinator = EngineExecutionCoordinator(
        service,
        provider_registry=FakeRegistry(FakeProvider()),
        tool_runtime=AsyncToolRuntime(
            admission_runtime=runtime,
        ),
        verification_hook=_verified_execution,
    )
    await coordinator.ensure_started(command)
    result = await _wait_result(
        service,
        command.execution_request.execution_id,
    )

    assert result.status == "completed"
    snapshot = ledger.snapshot("tenant-a")
    assert snapshot["active_reservations"] == 0
    assert snapshot["completions"] == 1
    assert snapshot["committed"]["operations"] == 1
    assert runtime.snapshot()["active_operations"] == ()
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_coordinator_rehydrates_execution_admission_after_local_restart(
    tmp_path,
) -> None:
    service, runtime, ledger = _admitted_service(tmp_path)
    _, command = _bundle(execution_id="exec-admission-restart")
    service.submit(
        command,
        verified_service_principal="codedock-backend",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now(),
    )
    first_lease = service.ensure_execution_admission(
        command,
        now=_now(),
    )
    assert first_lease is not None

    # Simulate process-local admission state loss while preserving the durable
    # tenant reservation. A fresh runtime against the same quota owner must
    # deterministically recover the same reservation.
    recovered_runtime = AdmissionRuntime(quota_ledger=ledger)
    recovered_service = EngineExecutionService(
        service.repository,
        service.submissions,
        service.authorities,
        admission_runtime=recovered_runtime,
    )
    recovered_lease = recovered_service.ensure_execution_admission(
        command,
        now=_now() + timedelta(seconds=1),
    )

    assert recovered_lease is not None
    assert recovered_lease.quota_reservation is not None
    assert first_lease.quota_reservation is not None
    assert (
        recovered_lease.quota_reservation.reservation_id
        == first_lease.quota_reservation.reservation_id
    )
    assert ledger.snapshot("tenant-a")["active_reservations"] == 1
