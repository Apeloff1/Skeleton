"""Retained checkpoints may be observed safely but never replay unbound work."""

from datetime import timedelta

import pytest

from skeleton.api.engine_runtime import EngineExecutionCoordinator
from skeleton.api.engine_service import EngineServiceError
from skeleton.contracts.ai_execution import AIExecutionResult, ExecutionState
from skeleton.intelligence.execution_runtime import CognitiveExecutionError, CognitiveExecutionRuntime
from skeleton.persistence.execution_repository import ExecutionRepositoryConflict
from skeleton.provider_contract import ProviderToolCall
from skeleton.skills.tool_runtime import AsyncToolRuntime
from skeleton.testing.test_engine_execution_coordinator import (
    FakeProvider, FakeRegistry, _bundle, _now, _service,
)


def _legacy_checkpoint(service, command, provider, *, expired=False, waiting=False):
    repo = service.repository
    runtime = CognitiveExecutionRuntime(repo, provider, AsyncToolRuntime())
    handoff = command.compiled_context
    payload = runtime._initial_payload(
        command.execution_request, instructions=handoff.instructions,
        prompt=handoff.prompt, history=(), context_digest=handoff.context_digest,
    )
    del payload["provider_execution_binding"]
    # A historical local-only pin does not establish the newer verifier,
    # cooperation, tenant and route identities.
    payload["local_provider_binding"] = {"identity": {"model_id": "old"}}
    if expired:
        payload["deadline"] = (_now() - timedelta(seconds=1)).isoformat()
    current = repo.get(command.execution_request.execution_id)
    if waiting:
        for state in (
            ExecutionState.LOADING, ExecutionState.ASSEMBLING_CONTEXT,
            ExecutionState.ROUTING, ExecutionState.PROVIDER_PENDING,
            ExecutionState.PROVIDER_COMPLETED, ExecutionState.CLASSIFYING_OUTPUT,
            ExecutionState.WAITING_FOR_TOOL_AUTHORITY,
        ):
            current = repo.transition(current.execution_id, state, expected_version=current.version)
        call = ProviderToolCall(call_id="call-upgrade", tool_id="repo.write", arguments={"path": "a"})
        payload["pending_tool_calls"] = [call.as_dict()]
        payload["pending_approval_call_ids"] = [call.call_id]
        payload["last_provider"] = {"turn_id": "legacy-turn"}
    repo.checkpoint(
        current.execution_id, payload, expected_execution_version=current.version,
        expected_checkpoint_version=current.checkpoint_version,
    )
    if waiting:
        current = repo.get(current.execution_id)
        repo.transition(current.execution_id, ExecutionState.WAITING_FOR_USER, expected_version=current.version)
    return runtime


@pytest.mark.parametrize(
    ("kind", "status", "error"),
    [("cancel", "cancelled", "cancellation_requested"),
     ("expired", "failed", "execution_deadline_exceeded"),
     ("unfinished", "failed", "provider_activation_binding_missing")],
)
@pytest.mark.asyncio
async def test_legacy_checkpoint_recovery_stops_without_provider_dispatch(tmp_path, kind, status, error):
    service = _service(tmp_path)
    _, command = _bundle(execution_id="legacy-" + kind)
    service.submit(command, verified_service_principal="codedock-backend", actor_id="actor-a", tenant_id="tenant-a")
    provider = FakeProvider()
    _legacy_checkpoint(service, command, provider, expired=kind == "expired")
    if kind == "cancel":
        service.cancel(command.execution_request.execution_id, verified_service_principal="codedock-backend",
                       actor_id="actor-a", tenant_id="tenant-a")
    coordinator = EngineExecutionCoordinator(service, provider_registry=FakeRegistry(provider), tool_runtime=AsyncToolRuntime())
    await coordinator._execute(command)
    result = service.repository.result(command.execution_request.execution_id)
    assert result is not None and result.status == status and result.usage["error_code"] == error
    assert provider.requests == []
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_legacy_pending_approval_can_be_observed_but_not_executed(tmp_path):
    service = _service(tmp_path)
    _, command = _bundle(execution_id="legacy-approval")
    service.submit(command, verified_service_principal="codedock-backend", actor_id="actor-a", tenant_id="tenant-a")
    provider = FakeProvider()
    runtime = _legacy_checkpoint(service, command, provider, waiting=True)
    observed = await runtime.resume(command.execution_request.execution_id)
    assert [item.call_id for item in observed.pending_approvals] == ["call-upgrade"]
    coordinator = EngineExecutionCoordinator(service, provider_registry=FakeRegistry(provider), tool_runtime=AsyncToolRuntime())
    await coordinator._execute(command)
    assert service.repository.result(command.execution_request.execution_id) is None
    assert service.repository.get(command.execution_request.execution_id).state is ExecutionState.WAITING_FOR_USER
    with pytest.raises(CognitiveExecutionError, match="lacks a pinned provider"):
        await runtime.resume(command.execution_request.execution_id, approval_refs={"call-upgrade": "approval-ref"})
    assert provider.requests == []
    assert service.repository.get(command.execution_request.execution_id).state is ExecutionState.WAITING_FOR_USER
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_committed_legacy_result_is_replayed_when_provider_unavailable(tmp_path):
    service = _service(tmp_path)
    _, command = _bundle(execution_id="legacy-committed")
    service.submit(command, verified_service_principal="codedock-backend", actor_id="actor-a", tenant_id="tenant-a")
    provider = FakeProvider()
    _legacy_checkpoint(service, command, provider)
    coordinator = EngineExecutionCoordinator(service, provider_registry=FakeRegistry(provider), tool_runtime=AsyncToolRuntime())
    await coordinator._execute(command)
    result = service.repository.result(command.execution_request.execution_id)
    assert result is not None and result.usage["error_code"] == "provider_activation_binding_missing"
    coordinator.provider_registry = FakeRegistry(unavailable=True)
    await coordinator._execute(command)
    assert service.repository.result(command.execution_request.execution_id) == result
    assert provider.requests == []
    await coordinator.shutdown()


@pytest.mark.parametrize(
    ("kind", "status", "error"),
    [("cancel", "cancelled", "cancellation_requested"),
     ("expired", "failed", "execution_deadline_exceeded")],
)
@pytest.mark.asyncio
async def test_unavailable_provider_does_not_preempt_passive_terminal_recovery(tmp_path, kind, status, error):
    service = _service(tmp_path)
    _, command = _bundle(execution_id="unavailable-" + kind)
    service.submit(command, verified_service_principal="codedock-backend", actor_id="actor-a", tenant_id="tenant-a")
    provider = FakeProvider()
    _legacy_checkpoint(service, command, provider, expired=kind == "expired")
    if kind == "cancel":
        service.cancel(command.execution_request.execution_id, verified_service_principal="codedock-backend",
                       actor_id="actor-a", tenant_id="tenant-a")
    coordinator = EngineExecutionCoordinator(service, provider_registry=FakeRegistry(unavailable=True), tool_runtime=AsyncToolRuntime())
    await coordinator._execute(command)
    result = service.repository.result(command.execution_request.execution_id)
    assert result is not None and result.status == status and result.usage["error_code"] == error
    assert provider.requests == []
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_unavailable_provider_preserves_passive_pending_approval(tmp_path, monkeypatch):
    service = _service(tmp_path)
    _, command = _bundle(execution_id="unavailable-approval")
    service.submit(command, verified_service_principal="codedock-backend", actor_id="actor-a", tenant_id="tenant-a")
    provider = FakeProvider()
    _legacy_checkpoint(service, command, provider, waiting=True)
    coordinator = EngineExecutionCoordinator(service, provider_registry=FakeRegistry(unavailable=True), tool_runtime=AsyncToolRuntime())
    await coordinator._execute(command)
    assert service.repository.result(command.execution_request.execution_id) is None
    assert service.repository.get(command.execution_request.execution_id).state is ExecutionState.WAITING_FOR_USER
    monkeypatch.setattr(service, "active_approval_refs", lambda _execution_id: {"call-upgrade": "approval-ref"})
    await coordinator._execute(command)
    assert service.repository.result(command.execution_request.execution_id) is None
    assert service.repository.get(command.execution_request.execution_id).state is ExecutionState.WAITING_FOR_USER
    assert provider.requests == []
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_passive_recovery_cannot_resume_approved_tool_or_publish_staged_output(tmp_path):
    service = _service(tmp_path)
    _, command = _bundle(execution_id="passive-boundaries")
    service.submit(command, verified_service_principal="codedock-backend", actor_id="actor-a", tenant_id="tenant-a")
    provider = FakeProvider()
    runtime = _legacy_checkpoint(service, command, provider, waiting=True)
    execution_id = command.execution_request.execution_id

    # Approval requires the pinned active provider before tool dispatch.
    assert runtime.recover_passively(execution_id, approval_refs={"call-upgrade": "approval-ref"}) is None
    assert service.repository.result(execution_id) is None
    current = service.repository.get(execution_id)
    staged = AIExecutionResult(
        operation_id=current.operation_id, execution_id=current.execution_id,
        status="completed", final_output="staged output", usage={}, completed_at=_now(),
    )
    service.repository.stage_finalization(staged, expected_execution_version=current.version)
    # Even passive cancellation cannot publish or replace a staged result.
    assert runtime.recover_passively(execution_id) is None
    assert service.repository.result(execution_id) is None
    assert provider.requests == []
    coordinator = EngineExecutionCoordinator(service, provider_registry=FakeRegistry(unavailable=True), tool_runtime=AsyncToolRuntime())
    await coordinator._execute(command)
    assert service.repository.result(execution_id) is None
    assert service.repository.finalization_intent(execution_id).result == staged
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_unavailable_provider_failure_cannot_overwrite_concurrently_staged_intent(tmp_path):
    service = _service(tmp_path)
    _, command = _bundle(execution_id="passive-atomic-intent")
    service.submit(command, verified_service_principal="codedock-backend", actor_id="actor-a", tenant_id="tenant-a")
    current = service.repository.get(command.execution_request.execution_id)
    staged = AIExecutionResult(operation_id=current.operation_id, execution_id=current.execution_id,
                               status="completed", final_output="retained", usage={}, completed_at=_now())
    service.repository.stage_finalization(staged, expected_execution_version=current.version)
    failure = AIExecutionResult(operation_id=current.operation_id, execution_id=current.execution_id,
                                status="failed", usage={"error_code": "provider_unavailable"}, completed_at=_now())
    with pytest.raises(ExecutionRepositoryConflict, match="staged finalization intent must be preserved"):
        service.repository.finalize(failure, expected_execution_version=current.version, require_no_staged_intent=True)
    assert service.repository.result(current.execution_id) is None
    assert service.repository.finalization_intent(current.execution_id).result == staged


@pytest.mark.asyncio
async def test_admission_denial_preserves_staged_finalization(tmp_path, monkeypatch):
    service = _service(tmp_path)
    _, command = _bundle(execution_id="staged-admission-denied")
    service.submit(command, verified_service_principal="codedock-backend", actor_id="actor-a", tenant_id="tenant-a")
    current = service.repository.get(command.execution_request.execution_id)
    staged = AIExecutionResult(operation_id=current.operation_id, execution_id=current.execution_id,
                               status="completed", final_output="retained", usage={}, completed_at=_now())
    service.repository.stage_finalization(staged, expected_execution_version=current.version)
    def deny(*_args, **_kwargs):
        raise EngineServiceError("admission unavailable")
    monkeypatch.setattr(service, "ensure_execution_admission", deny)
    coordinator = EngineExecutionCoordinator(service, provider_registry=FakeRegistry(unavailable=True), tool_runtime=AsyncToolRuntime())
    await coordinator._execute(command)
    assert service.repository.result(current.execution_id) is None
    assert service.repository.finalization_intent(current.execution_id).result == staged
    await coordinator.shutdown()


@pytest.mark.parametrize("kind", ["cancel", "expired", "waiting", "unfinished"])
@pytest.mark.asyncio
async def test_admission_denial_preserves_checkpoint_for_metered_retry(tmp_path, monkeypatch, kind):
    service = _service(tmp_path)
    _, command = _bundle(execution_id="admission-retry-" + kind)
    service.submit(command, verified_service_principal="codedock-backend", actor_id="actor-a", tenant_id="tenant-a")
    provider = FakeProvider()
    _legacy_checkpoint(service, command, provider, expired=kind == "expired", waiting=kind == "waiting")
    execution_id = command.execution_request.execution_id
    if kind == "cancel":
        service.cancel(execution_id, verified_service_principal="codedock-backend", actor_id="actor-a", tenant_id="tenant-a")
    before = service.repository.latest_checkpoint(execution_id)
    original = service.ensure_execution_admission
    def deny(*_args, **_kwargs):
        raise EngineServiceError("admission unavailable")
    monkeypatch.setattr(service, "ensure_execution_admission", deny)
    coordinator = EngineExecutionCoordinator(service, provider_registry=FakeRegistry(unavailable=True), tool_runtime=AsyncToolRuntime())
    await coordinator._execute(command)
    assert service.repository.result(execution_id) is None
    assert service.repository.latest_checkpoint(execution_id) == before
    assert coordinator.supervision_snapshot()["recovery"]["admission_deferred"] == 1
    assert provider.requests == []
    monkeypatch.setattr(service, "ensure_execution_admission", original)
    await coordinator._execute(command)
    result = service.repository.result(execution_id)
    if kind == "cancel":
        assert result is not None and result.status == "cancelled"
    elif kind == "expired":
        assert result is not None and result.usage["error_code"] == "execution_deadline_exceeded"
    else:
        assert result is None
    assert provider.requests == []
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_admission_denial_without_checkpoint_still_finishes_as_denied(tmp_path, monkeypatch):
    service = _service(tmp_path)
    _, command = _bundle(execution_id="new-admission-denied")
    service.submit(command, verified_service_principal="codedock-backend", actor_id="actor-a", tenant_id="tenant-a")
    def deny(*_args, **_kwargs):
        raise EngineServiceError("admission unavailable")
    monkeypatch.setattr(service, "ensure_execution_admission", deny)
    coordinator = EngineExecutionCoordinator(service, provider_registry=FakeRegistry(unavailable=True), tool_runtime=AsyncToolRuntime())
    await coordinator._execute(command)
    result = service.repository.result(command.execution_request.execution_id)
    assert result is not None and result.usage["error_code"] == "execution_admission_denied"
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_admission_denial_cannot_replace_concurrently_created_checkpoint(tmp_path, monkeypatch):
    service = _service(tmp_path)
    _, command = _bundle(execution_id="admission-checkpoint-race")
    service.submit(command, verified_service_principal="codedock-backend", actor_id="actor-a", tenant_id="tenant-a")
    provider = FakeProvider()
    def deny(*_args, **_kwargs):
        raise EngineServiceError("admission unavailable")
    monkeypatch.setattr(service, "ensure_execution_admission", deny)
    original_finalize = service.repository.finalize
    def checkpoint_before_finalize(*args, **kwargs):
        _legacy_checkpoint(service, command, provider)
        return original_finalize(*args, **kwargs)
    monkeypatch.setattr(service.repository, "finalize", checkpoint_before_finalize)
    coordinator = EngineExecutionCoordinator(service, provider_registry=FakeRegistry(unavailable=True), tool_runtime=AsyncToolRuntime())
    await coordinator._drive(command)
    execution_id = command.execution_request.execution_id
    assert service.repository.result(execution_id) is None
    assert service.repository.latest_checkpoint(execution_id) is not None
    assert provider.requests == []
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_passive_recovery_meter_failure_does_not_bypass_metering(tmp_path, monkeypatch):
    service = _service(tmp_path)
    _, command = _bundle(execution_id="passive-meter-failure")
    service.submit(command, verified_service_principal="codedock-backend", actor_id="actor-a", tenant_id="tenant-a")
    _legacy_checkpoint(service, command, FakeProvider(), expired=True)
    def unavailable_meter(*_args, **_kwargs):
        raise RuntimeError("meter unavailable")
    monkeypatch.setattr(service, "meter_execution_storage", unavailable_meter)
    coordinator = EngineExecutionCoordinator(service, provider_registry=FakeRegistry(unavailable=True), tool_runtime=AsyncToolRuntime())
    await coordinator._drive(command)
    assert service.repository.result(command.execution_request.execution_id) is None
    assert service.repository.finalization_intent(command.execution_request.execution_id) is None
    assert coordinator._driver_failures == 1
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_unbound_staged_result_is_not_published(tmp_path):
    service = _service(tmp_path)
    _, command = _bundle(execution_id="legacy-staged")
    service.submit(command, verified_service_principal="codedock-backend", actor_id="actor-a", tenant_id="tenant-a")
    provider = FakeProvider()
    _legacy_checkpoint(service, command, provider)
    current = service.repository.get(command.execution_request.execution_id)
    staged = AIExecutionResult(
        operation_id=current.operation_id, execution_id=current.execution_id,
        status="completed", final_output="unverified staged content", usage={}, completed_at=_now(),
    )
    service.repository.stage_finalization(staged, expected_execution_version=current.version)
    coordinator = EngineExecutionCoordinator(service, provider_registry=FakeRegistry(provider), tool_runtime=AsyncToolRuntime())
    await coordinator._execute(command)
    result = service.repository.result(current.execution_id)
    assert result is None
    assert service.repository.finalization_intent(current.execution_id).result == staged
    assert provider.requests == []
    await coordinator.shutdown()
