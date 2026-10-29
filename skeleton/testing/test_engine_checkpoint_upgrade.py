"""Retained checkpoints may be observed safely but never replay unbound work."""

from datetime import timedelta

import pytest

from skeleton.api.engine_runtime import EngineExecutionCoordinator
from skeleton.contracts.ai_execution import AIExecutionResult, ExecutionState
from skeleton.intelligence.execution_runtime import CognitiveExecutionError, CognitiveExecutionRuntime
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
    assert result.status == "failed" and result.usage["error_code"] == "provider_activation_binding_missing"
    assert result.final_output is None
    assert provider.requests == []
    await coordinator.shutdown()
