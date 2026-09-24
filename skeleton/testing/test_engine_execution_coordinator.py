from __future__ import annotations

import asyncio
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
from skeleton.persistence.execution_repository import SQLiteExecutionRepository
from skeleton.provider_contract import FinishReason, ProviderUsage
from skeleton.provider_runtime import ProviderResponse
from skeleton.skills.tool_runtime import AsyncToolRuntime


def _now() -> datetime:
    return datetime(2026, 9, 23, 20, 30, tzinfo=timezone.utc)


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
    operation = OperationEnvelope(
        operation_id=str(uuid4()),
        tenant_id="tenant-a",
        actor_id="actor-a",
        capability="assistant.chat",
        created_at=_now(),
        deadline=_now() + timedelta(minutes=5),
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
        ),
        capability=operation.capability,
        issued_at=_now(),
        expires_at=_now() + timedelta(minutes=5),
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
                    }
                ),
                tenant_ids=frozenset({"tenant-a"}),
                capabilities=frozenset({"assistant.chat"}),
            )
        ]
    )
    return EngineExecutionService(repo, submissions, registry)


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
        now=_now(),
    )
    provider = FakeProvider()
    coordinator = EngineExecutionCoordinator(
        service,
        provider_registry=FakeRegistry(provider),
        tool_runtime=AsyncToolRuntime(),
    )

    await coordinator.ensure_started(command)
    result = await _wait_result(service, command.execution_request.execution_id)

    assert result.status == "completed"
    assert result.final_output == "engine answer"
    assert result.verification_receipt["outcome"] == "verified"
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
        now=_now(),
    )
    assert status.operation_state == "completed"
    events = service.events(
        command.execution_request.execution_id,
        verified_service_principal="codedock-backend",
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
        now=_now(),
    )
    gate = asyncio.Event()
    provider = FakeProvider(gate=gate)
    coordinator = EngineExecutionCoordinator(
        service,
        provider_registry=FakeRegistry(provider),
        tool_runtime=AsyncToolRuntime(),
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
async def test_coordinator_restart_recovery_uses_durable_submission(tmp_path) -> None:
    service = _service(tmp_path)
    _, command = _bundle()
    service.submit(
        command,
        verified_service_principal="codedock-backend",
        now=_now(),
    )

    provider = FakeProvider(text="recovered")
    recovered = EngineExecutionCoordinator(
        service,
        provider_registry=FakeRegistry(provider),
        tool_runtime=AsyncToolRuntime(),
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
        now=_now(),
    )
    coordinator = EngineExecutionCoordinator(
        service,
        provider_registry=FakeRegistry(unavailable=True),
        tool_runtime=AsyncToolRuntime(),
    )

    await coordinator.ensure_started(command)
    result = await _wait_result(service, command.execution_request.execution_id)

    assert result.status == "failed"
    assert result.usage["error_code"] == "provider_unavailable"
    await coordinator.shutdown()
