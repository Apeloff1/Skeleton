from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from skeleton.api.engine_authority import (
    DelegatedAuthority,
    EngineAuthorityError,
    EngineAuthorityRegistry,
    EngineServiceGrant,
    engine_request_binding,
)
from skeleton.api.engine_service import (
    EngineContextHandoff,
    EngineExecutionCommand,
    EngineExecutionService,
    EngineServiceError,
    EngineSubmissionConflict,
    SQLiteEngineSubmissionStore,
)
from skeleton.contracts.ai_execution import (
    AIExecutionRequest,
    AgentTurn,
    ExecutionState,
)
from skeleton.contracts.operation import OperationEnvelope
from skeleton.intelligence.admission_runtime import AdmissionRuntime
from skeleton.intelligence.quota import TenantQuota, TenantQuotaLedger
from skeleton.persistence.execution_repository import SQLiteExecutionRepository
from skeleton.vault.data_lifecycle import DataLifecycleRegistry
from skeleton.vault.governance_registry import GovernanceRegistry
from skeleton.vault.lifecycle_adapters import (
    LifecycleAdapterRegistry,
    LifecycleExecutor,
)
from skeleton.provider_contract import ProviderToolCall
from skeleton.skills.tool_contract import (
    ToolExecutionRequest,
    ToolExecutionStatus,
    ToolManifest,
)
from skeleton.skills.tool_runtime import AsyncToolRuntime


def _now() -> datetime:
    return datetime(2026, 9, 23, 20, 0, tzinfo=timezone.utc)


def _operation(
    *,
    operation_id: str | None = None,
    tenant_id: str = "tenant-a",
    actor_id: str = "actor-a",
    capability: str = "assistant.chat",
    idempotency_key: str = "idem-1",
    created_at: datetime | None = None,
    deadline: datetime | None = None,
    trace_id: str = "trace-1",
) -> OperationEnvelope:
    started = created_at or _now()
    return OperationEnvelope(
        operation_id=operation_id or str(uuid4()),
        tenant_id=tenant_id,
        actor_id=actor_id,
        capability=capability,
        created_at=started,
        deadline=deadline or (started + timedelta(minutes=10)),
        idempotency_key=idempotency_key,
        trace_id=trace_id,
    )


def _handoff(
    operation: OperationEnvelope,
    *,
    execution_id: str = "exec-1",
) -> EngineContextHandoff:
    return EngineContextHandoff(
        operation_id=operation.operation_id,
        execution_id=execution_id,
        turn_id="turn-1",
        tenant_id=operation.tenant_id,
        context_id="context-1",
        context_digest="a" * 64,
        compiler_version="test-compiler",
        source_snapshot=(("segment-1", "b" * 64),),
        data_class="internal",
        instructions="Follow the canonical policy.",
        prompt="Answer the canonical request.",
    )


def _execution_request(
    operation: OperationEnvelope,
    *,
    execution_id: str = "exec-1",
    objective: str = "Answer the request.",
    created_at: datetime | None = None,
) -> AIExecutionRequest:
    return AIExecutionRequest(
        operation_id=operation.operation_id,
        execution_id=execution_id,
        objective=objective,
        context_policy={
            "tenant_id": operation.tenant_id,
            "capability": operation.capability,
            "data_class": "internal",
            "context_id": "context-1",
            "context_digest": "a" * 64,
            "compiler_version": "test-compiler",
            "handoff_digest": _handoff(
                operation,
                execution_id=execution_id,
            ).handoff_digest,
            "source_snapshot": [["segment-1", "b" * 64]],
        },
        tool_policy={
            "tenant_id": operation.tenant_id,
            "allowed_tool_ids": [],
        },
        resource_budget={
            "max_model_turns": 4,
            "max_tool_calls": 4,
        },
        stop_policy={"max_repeat_tool_batches": 1},
        created_at=created_at or _now(),
    )


def _authority(
    operation: OperationEnvelope,
    execution_request: AIExecutionRequest,
    *,
    service_principal: str = "backend-service",
    scopes=(
        "engine:submit",
        "engine:read",
        "engine:cancel",
        "engine:events",
        "engine:approve",
        "engine:admission",
    ),
    issued_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> DelegatedAuthority:
    return DelegatedAuthority(
        service_principal=service_principal,
        actor_id=operation.actor_id,
        tenant_id=operation.tenant_id,
        scopes=tuple(scopes),
        capability=operation.capability,
        issued_at=issued_at or _now(),
        expires_at=expires_at or ((issued_at or _now()) + timedelta(minutes=5)),
        request_binding=engine_request_binding(operation, execution_request),
    )


def _command(
    *,
    operation: OperationEnvelope | None = None,
    execution_request: AIExecutionRequest | None = None,
    authority: DelegatedAuthority | None = None,
) -> EngineExecutionCommand:
    operation = operation or _operation()
    execution_request = execution_request or _execution_request(operation)
    authority = authority or _authority(operation, execution_request)
    return EngineExecutionCommand(
        operation=operation,
        execution_request=execution_request,
        delegated_authority=authority,
        compiled_context=_handoff(
            operation,
            execution_id=execution_request.execution_id,
        ),
        context_seed_refs=("conversation:thread-1",),
        resource_budget=dict(execution_request.resource_budget),
        stream_preferences={"mode": "events"},
    )


def _registry(
    *,
    scopes=(
        "engine:submit",
        "engine:read",
        "engine:cancel",
        "engine:events",
        "engine:approve",
        "engine:admission",
    ),
) -> EngineAuthorityRegistry:
    return EngineAuthorityRegistry(
        [
            EngineServiceGrant(
                service_principal="backend-service",
                scopes=frozenset(scopes),
                tenant_ids=frozenset({"tenant-a"}),
                capabilities=frozenset({"assistant.chat"}),
            )
        ]
    )


def _service(tmp_path, *, registry=None):
    return EngineExecutionService(
        SQLiteExecutionRepository(tmp_path / "execution.sqlite3"),
        SQLiteEngineSubmissionStore(tmp_path / "submissions.sqlite3"),
        registry or _registry(),
    )



def _admitted_service(tmp_path):
    ledger = TenantQuotaLedger()
    runtime = AdmissionRuntime(
        quota_ledger=ledger,
        default_tenant_quota=TenantQuota(
            window_id="engine-test-window",
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
    service = EngineExecutionService(
        SQLiteExecutionRepository(tmp_path / "execution-admitted.sqlite3"),
        SQLiteEngineSubmissionStore(tmp_path / "submissions-admitted.sqlite3"),
        _registry(),
        admission_runtime=runtime,
    )
    return service, runtime, ledger


def test_command_rejects_tool_policy_handoff_mismatch() -> None:
    operation = _operation()
    base = _execution_request(operation)
    request = AIExecutionRequest(
        operation_id=base.operation_id,
        execution_id=base.execution_id,
        objective=base.objective,
        context_policy=dict(base.context_policy),
        tool_policy={
            "tenant_id": operation.tenant_id,
            "allowed_tool_ids": ["repo.read"],
        },
        resource_budget=dict(base.resource_budget),
        stop_policy=dict(base.stop_policy),
        created_at=base.created_at,
    )
    authority = _authority(operation, request)

    with pytest.raises(
        EngineServiceError,
        match="tools do not match execution tool policy",
    ):
        EngineExecutionCommand(
            operation=operation,
            execution_request=request,
            delegated_authority=authority,
            compiled_context=_handoff(
                operation,
                execution_id=request.execution_id,
            ),
            context_seed_refs=("conversation:thread-1",),
            resource_budget=dict(request.resource_budget),
            stream_preferences={"mode": "events"},
        )


def test_submit_is_idempotent_and_ack_survives_service_restart(tmp_path) -> None:
    command = _command()
    service = _service(tmp_path)

    first = service.submit(
        command,
        verified_service_principal="backend-service",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now(),
    )

    restarted = _service(tmp_path)
    replay = restarted.submit(
        command,
        verified_service_principal="backend-service",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now() + timedelta(seconds=30),
    )

    assert replay == first
    assert first.execution_id == "exec-1"
    assert first.state == "admitted"
    assert first.status_ref.endswith("/exec-1")
    assert first.events_ref.endswith("/exec-1/events")


def test_submit_retry_accepts_fresh_temporal_authority_for_same_work(
    tmp_path,
) -> None:
    operation_id = str(uuid4())
    first_operation = _operation(operation_id=operation_id)
    first_request = _execution_request(first_operation)
    first_command = _command(
        operation=first_operation,
        execution_request=first_request,
        authority=_authority(first_operation, first_request),
    )
    service = _service(tmp_path)
    first_ack = service.submit(
        first_command,
        verified_service_principal="backend-service",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now(),
    )

    retry_started = _now() + timedelta(seconds=30)
    retry_operation = _operation(
        operation_id=operation_id,
        created_at=retry_started,
        deadline=retry_started + timedelta(minutes=10),
        trace_id="trace-retry",
    )
    retry_request = _execution_request(
        retry_operation,
        created_at=retry_started,
    )
    retry_command = _command(
        operation=retry_operation,
        execution_request=retry_request,
        authority=_authority(
            retry_operation,
            retry_request,
            issued_at=retry_started,
            expires_at=retry_started + timedelta(minutes=5),
        ),
    )

    assert retry_command.command_digest != first_command.command_digest
    assert retry_command.submission_digest == first_command.submission_digest

    replay = service.submit(
        retry_command,
        verified_service_principal="backend-service",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=retry_started,
    )

    assert replay == first_ack


def test_submit_conflicting_retry_is_rejected(tmp_path) -> None:
    operation = _operation()
    first_request = _execution_request(operation, objective="First objective")
    first = _command(
        operation=operation,
        execution_request=first_request,
        authority=_authority(operation, first_request),
    )
    service = _service(tmp_path)
    service.submit(
        first,
        verified_service_principal="backend-service",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now(),
    )

    changed_request = _execution_request(
        operation,
        objective="Changed objective",
    )
    changed = _command(
        operation=operation,
        execution_request=changed_request,
        authority=_authority(operation, changed_request),
    )

    with pytest.raises(EngineSubmissionConflict, match="different command"):
        service.submit(
            changed,
            verified_service_principal="backend-service",
            now=_now(),
        )


def test_submit_rejects_scope_escalation_beyond_server_grant(tmp_path) -> None:
    operation = _operation()
    execution_request = _execution_request(operation)
    authority = _authority(
        operation,
        execution_request,
        scopes=("engine:submit", "engine:admin"),
    )
    command = _command(
        operation=operation,
        execution_request=execution_request,
        authority=authority,
    )
    service = _service(
        tmp_path,
        registry=_registry(scopes=("engine:submit",)),
    )

    with pytest.raises(EngineAuthorityError, match="exceed"):
        service.submit(
            command,
            verified_service_principal="backend-service",
            now=_now(),
        )


def test_submit_rejects_tenant_mismatch(tmp_path) -> None:
    operation = _operation()
    execution_request = _execution_request(operation)
    authority = DelegatedAuthority(
        service_principal="backend-service",
        actor_id=operation.actor_id,
        tenant_id="tenant-b",
        scopes=(
            "engine:submit",
            "engine:read",
            "engine:cancel",
            "engine:events",
        ),
        capability=operation.capability,
        issued_at=_now(),
        expires_at=_now() + timedelta(minutes=5),
        request_binding=engine_request_binding(operation, execution_request),
    )
    command = _command(
        operation=operation,
        execution_request=execution_request,
        authority=authority,
    )

    with pytest.raises(EngineAuthorityError, match="tenant"):
        _service(tmp_path).submit(
            command,
            verified_service_principal="backend-service",
            now=_now(),
        )


def test_expired_delegation_cannot_submit(tmp_path) -> None:
    operation = _operation()
    execution_request = _execution_request(operation)
    authority = _authority(
        operation,
        execution_request,
        expires_at=_now() + timedelta(seconds=1),
    )
    command = _command(
        operation=operation,
        execution_request=execution_request,
        authority=authority,
    )

    with pytest.raises(EngineAuthorityError, match="expired"):
        _service(tmp_path).submit(
            command,
            verified_service_principal="backend-service",
            now=_now() + timedelta(seconds=2),
        )


def test_status_access_is_bound_to_owning_service_principal(tmp_path) -> None:
    service = _service(tmp_path)
    command = _command()
    service.submit(
        command,
        verified_service_principal="backend-service",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now(),
    )

    status = service.status(
        "exec-1",
        verified_service_principal="backend-service",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now() + timedelta(hours=1),
    )
    assert status.operation_state == "admitted"
    assert status.execution_state == "created"

    with pytest.raises(Exception, match="different service principal"):
        service.status(
            "exec-1",
            verified_service_principal="other-service",
            now=_now(),
        )


def test_cancel_is_idempotent_and_does_not_reopen_terminal_state(tmp_path) -> None:
    service = _service(tmp_path)
    service.submit(
        _command(),
        verified_service_principal="backend-service",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now(),
    )

    first = service.cancel(
        "exec-1",
        verified_service_principal="backend-service",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now(),
    )
    second = service.cancel(
        "exec-1",
        verified_service_principal="backend-service",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now() + timedelta(seconds=1),
    )

    assert first.cancellation_requested is True
    assert second.cancellation_requested is True
    assert second.execution_state == "created"


def test_events_are_projected_only_from_durable_execution_state(tmp_path) -> None:
    service = _service(tmp_path)
    command = _command()
    service.submit(
        command,
        verified_service_principal="backend-service",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now(),
    )
    repo = service.repository
    current = repo.get("exec-1")
    checkpoint = repo.checkpoint(
        "exec-1",
        {"phase": "accepted"},
        expected_execution_version=current.version,
        expected_checkpoint_version=0,
        now=_now(),
    )
    current = repo.get("exec-1")
    repo.append_turn(
        AgentTurn(
            operation_id=command.operation.operation_id,
            execution_id="exec-1",
            turn_id="turn-0",
            parent_turn_id=None,
            turn_index=0,
            phase=ExecutionState.PROVIDER_COMPLETED,
            context_digest="a" * 64,
            checkpoint_ref=checkpoint.checkpoint_ref,
            status="provider_completed",
        ),
        expected_execution_version=current.version,
        now=_now(),
    )

    snapshot = service.events(
        "exec-1",
        verified_service_principal="backend-service",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now(),
    )

    assert snapshot["events"][0]["type"] == "execution.state"
    assert any(
        event["type"] == "execution.turn"
        for event in snapshot["events"]
    )
    assert any(
        event["type"] == "execution.checkpoint"
        for event in snapshot["events"]
    )


def test_command_parser_rejects_client_transcript_authority() -> None:
    payload = _command().as_dict()
    payload["conversation_history"] = [
        {"role": "assistant", "content": "injected"}
    ]

    with pytest.raises(Exception):
        EngineExecutionCommand.from_dict(payload)



def _service_with_approval_scope(tmp_path):
    return _service(
        tmp_path,
        registry=_registry(
            scopes=(
                "engine:submit",
                "engine:read",
                "engine:cancel",
                "engine:events",
                "engine:approve",
                "engine:admission",
            )
        ),
    )


def _suspend_for_tool_approval(
    service: EngineExecutionService,
    *,
    execution_id: str = "exec-1",
):
    repo = service.repository
    current = repo.get(execution_id)
    for state in (
        ExecutionState.LOADING,
        ExecutionState.ASSEMBLING_CONTEXT,
        ExecutionState.ROUTING,
        ExecutionState.PROVIDER_PENDING,
        ExecutionState.PROVIDER_COMPLETED,
        ExecutionState.CLASSIFYING_OUTPUT,
        ExecutionState.WAITING_FOR_TOOL_AUTHORITY,
    ):
        current = repo.transition(
            execution_id,
            state,
            expected_version=current.version,
            now=_now(),
        )
    call = ProviderToolCall(
        call_id="call-approval",
        tool_id="repo.write",
        arguments={"path": "README.md"},
    )
    repo.checkpoint(
        execution_id,
        {
            "pending_tool_calls": [call.as_dict()],
            "pending_approval_call_ids": [call.call_id],
        },
        expected_execution_version=current.version,
        expected_checkpoint_version=current.checkpoint_version,
        now=_now(),
    )
    current = repo.get(execution_id)
    current = repo.transition(
        execution_id,
        ExecutionState.WAITING_FOR_USER,
        expected_version=current.version,
        now=_now(),
    )
    return call, current


def test_tool_approval_is_bound_to_current_pending_call_and_survives_restart(
    tmp_path,
) -> None:
    service = _service_with_approval_scope(tmp_path)
    command = _command()
    service.submit(
        command,
        verified_service_principal="backend-service",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now(),
    )
    call, _ = _suspend_for_tool_approval(service)

    pending = service.pending_tool_approvals(
        "exec-1",
        verified_service_principal="backend-service",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now(),
    )
    assert len(pending) == 1
    row = pending[0]
    assert row["call_id"] == call.call_id
    assert row["tool_id"] == call.tool_id
    assert row["arguments_digest"] == call.arguments_digest
    assert row["idempotency_key"]
    assert row["approval_ref"].startswith("approval:")

    approval = service.approve_tool_call(
        "exec-1",
        verified_service_principal="backend-service",
        actor_id="actor-a",
        tenant_id="tenant-a",
        call_id=call.call_id,
        tool_id=call.tool_id,
        arguments_digest=call.arguments_digest,
        idempotency_key=row["idempotency_key"],
        expires_at=_now() + timedelta(minutes=5),
        now=_now(),
    )
    replay = service.approve_tool_call(
        "exec-1",
        verified_service_principal="backend-service",
        actor_id="actor-a",
        tenant_id="tenant-a",
        call_id=call.call_id,
        tool_id=call.tool_id,
        arguments_digest=call.arguments_digest,
        idempotency_key=row["idempotency_key"],
        expires_at=_now() + timedelta(minutes=5),
        now=_now() + timedelta(seconds=30),
    )

    assert replay == approval
    assert service.active_approval_refs(
        "exec-1",
        now=_now(),
    ) == {call.call_id: approval.approval_ref}

    restarted = _service_with_approval_scope(tmp_path)
    assert restarted.active_approval_refs(
        "exec-1",
        now=_now() + timedelta(minutes=1),
    ) == {call.call_id: approval.approval_ref}


def test_tool_approval_rejects_expired_and_mismatched_decisions(tmp_path) -> None:
    service = _service_with_approval_scope(tmp_path)
    service.submit(
        _command(),
        verified_service_principal="backend-service",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now(),
    )
    call, _ = _suspend_for_tool_approval(service)

    with pytest.raises(Exception, match="already expired"):
        service.approve_tool_call(
            "exec-1",
            verified_service_principal="backend-service",
            actor_id="actor-a",
            tenant_id="tenant-a",
            call_id=call.call_id,
            tool_id=call.tool_id,
            arguments_digest=call.arguments_digest,
            idempotency_key="expired",
            expires_at=_now() - timedelta(seconds=1),
            now=_now(),
        )

    with pytest.raises(Exception, match="does not match"):
        service.approve_tool_call(
            "exec-1",
            verified_service_principal="backend-service",
            actor_id="actor-a",
            tenant_id="tenant-a",
            call_id=call.call_id,
            tool_id="repo.other",
            arguments_digest=call.arguments_digest,
            idempotency_key="wrong-tool",
            expires_at=_now() + timedelta(minutes=5),
            now=_now(),
        )

    with pytest.raises(Exception, match="does not match"):
        service.approve_tool_call(
            "exec-1",
            verified_service_principal="backend-service",
            actor_id="actor-a",
            tenant_id="tenant-a",
            call_id=call.call_id,
            tool_id=call.tool_id,
            arguments_digest="0" * 64,
            idempotency_key="wrong-digest",
            expires_at=_now() + timedelta(minutes=5),
            now=_now(),
        )

    assert service.active_approval_refs("exec-1", now=_now()) == {}


def test_expired_persisted_approval_is_not_replayed_into_resume(tmp_path) -> None:
    service = _service_with_approval_scope(tmp_path)
    service.submit(
        _command(),
        verified_service_principal="backend-service",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now(),
    )
    call, _ = _suspend_for_tool_approval(service)
    pending = service.pending_tool_approvals(
        "exec-1",
        verified_service_principal="backend-service",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now(),
    )
    approval = service.approve_tool_call(
        "exec-1",
        verified_service_principal="backend-service",
        actor_id="actor-a",
        tenant_id="tenant-a",
        call_id=call.call_id,
        tool_id=call.tool_id,
        arguments_digest=call.arguments_digest,
        idempotency_key=pending[0]["idempotency_key"],
        expires_at=_now() + timedelta(seconds=1),
        now=_now(),
    )

    assert service.active_approval_refs(
        "exec-1",
        now=_now(),
    ) == {call.call_id: approval.approval_ref}
    assert service.active_approval_refs(
        "exec-1",
        now=_now() + timedelta(seconds=2),
    ) == {}



def test_expired_delegation_blocks_mutating_access_but_allows_audit_reads(
    tmp_path,
) -> None:
    operation = _operation()
    request = _execution_request(operation)
    authority = _authority(
        operation,
        request,
        expires_at=_now() + timedelta(seconds=1),
    )
    command = _command(
        operation=operation,
        execution_request=request,
        authority=authority,
    )
    service = _service_with_approval_scope(tmp_path)
    service.submit(
        command,
        verified_service_principal="backend-service",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now(),
    )

    status = service.status(
        "exec-1",
        verified_service_principal="backend-service",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now() + timedelta(seconds=2),
    )
    events = service.events(
        "exec-1",
        verified_service_principal="backend-service",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now() + timedelta(seconds=2),
    )
    assert status.execution_state == "created"
    assert events["events"]

    with pytest.raises(EngineAuthorityError, match="expired"):
        service.cancel(
            "exec-1",
            verified_service_principal="backend-service",
            actor_id="actor-a",
            tenant_id="tenant-a",
            now=_now() + timedelta(seconds=2),
        )


def test_tool_approval_expiry_cannot_outlive_delegated_authority(
    tmp_path,
) -> None:
    operation = _operation()
    request = _execution_request(operation)
    authority = _authority(
        operation,
        request,
        expires_at=_now() + timedelta(minutes=2),
    )
    command = _command(
        operation=operation,
        execution_request=request,
        authority=authority,
    )
    service = _service_with_approval_scope(tmp_path)
    service.submit(
        command,
        verified_service_principal="backend-service",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now(),
    )
    call, _ = _suspend_for_tool_approval(service)

    with pytest.raises(Exception, match="exceeds delegated authority window"):
        service.approve_tool_call(
            "exec-1",
            verified_service_principal="backend-service",
            actor_id="actor-a",
            tenant_id="tenant-a",
            call_id=call.call_id,
            tool_id=call.tool_id,
            arguments_digest=call.arguments_digest,
            idempotency_key="too-long",
            expires_at=_now() + timedelta(minutes=3),
            now=_now(),
        )


def test_active_approval_refs_fail_closed_after_delegation_expiry(
    tmp_path,
) -> None:
    operation = _operation()
    request = _execution_request(operation)
    authority = _authority(
        operation,
        request,
        expires_at=_now() + timedelta(minutes=2),
    )
    command = _command(
        operation=operation,
        execution_request=request,
        authority=authority,
    )
    service = _service_with_approval_scope(tmp_path)
    service.submit(
        command,
        verified_service_principal="backend-service",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now(),
    )
    call, _ = _suspend_for_tool_approval(service)
    pending = service.pending_tool_approvals(
        "exec-1",
        verified_service_principal="backend-service",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now(),
    )
    approval = service.approve_tool_call(
        "exec-1",
        verified_service_principal="backend-service",
        actor_id="actor-a",
        tenant_id="tenant-a",
        call_id=call.call_id,
        tool_id=call.tool_id,
        arguments_digest=call.arguments_digest,
        idempotency_key=pending[0]["idempotency_key"],
        expires_at=_now() + timedelta(seconds=90),
        now=_now(),
    )
    assert service.active_approval_refs(
        "exec-1",
        now=_now() + timedelta(seconds=60),
    ) == {call.call_id: approval.approval_ref}
    assert service.active_approval_refs(
        "exec-1",
        now=_now() + timedelta(minutes=3),
    ) == {}


def test_engine_approval_uses_request_bound_runtime_capability(tmp_path) -> None:
    service = _service_with_approval_scope(tmp_path)
    command = _command()
    service.submit(
        command,
        verified_service_principal="backend-service",
        actor_id=command.operation.actor_id,
        tenant_id=command.operation.tenant_id,
        now=_now(),
    )
    call, _ = _suspend_for_tool_approval(
        service,
        execution_id=command.execution_request.execution_id,
    )

    pending = service.pending_tool_approvals(
        command.execution_request.execution_id,
        verified_service_principal="backend-service",
        actor_id=command.operation.actor_id,
        tenant_id=command.operation.tenant_id,
        now=_now(),
    )
    assert len(pending) == 1
    row = pending[0]
    assert row["approval_ref"].startswith("approval:")

    approval = service.approve_tool_call(
        command.execution_request.execution_id,
        verified_service_principal="backend-service",
        actor_id=command.operation.actor_id,
        tenant_id=command.operation.tenant_id,
        call_id=call.call_id,
        tool_id=call.tool_id,
        arguments_digest=str(call.arguments_digest),
        idempotency_key=row["idempotency_key"],
        expires_at=_now() + timedelta(minutes=5),
        now=_now(),
    )
    assert approval.approval_ref == row["approval_ref"]

    with pytest.raises(
        EngineServiceError,
        match="idempotency_key does not match pending call",
    ):
        service.approve_tool_call(
            command.execution_request.execution_id,
            verified_service_principal="backend-service",
            actor_id=command.operation.actor_id,
            tenant_id=command.operation.tenant_id,
            call_id=call.call_id,
            tool_id=call.tool_id,
            arguments_digest=str(call.arguments_digest),
            idempotency_key="tampered-idempotency",
            expires_at=_now() + timedelta(minutes=5),
            now=_now(),
        )

def test_submit_acquires_execution_quota_before_durable_allocation(
    tmp_path,
) -> None:
    service, runtime, ledger = _admitted_service(tmp_path)
    command = _command()

    ack = service.submit(
        command,
        verified_service_principal="backend-service",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now(),
    )

    assert ack.execution_id == command.execution_request.execution_id
    assert service.repository.get(ack.execution_id).execution_id == ack.execution_id
    snapshot = ledger.snapshot("tenant-a")
    assert snapshot["active_reservations"] == 1
    assert snapshot["reserved"]["operations"] == 1
    assert len(runtime.snapshot()["active_operations"]) == 1


@pytest.mark.asyncio
async def test_execution_quota_lease_is_shared_with_tool_usage(
    tmp_path,
) -> None:
    service, runtime, ledger = _admitted_service(tmp_path)
    command = _command()
    service.submit(
        command,
        verified_service_principal="backend-service",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now(),
    )
    lease = service.ensure_execution_admission(
        command,
        now=_now(),
    )
    assert lease is not None

    tools = AsyncToolRuntime(admission_runtime=runtime)

    async def handler(_request):
        return "artifact:engine-admission-test"

    await tools.register(
        ToolManifest(
            tool_id="repo.read",
            version="1.0.0",
            description="Read bounded repository state.",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
        ),
        handler,
    )
    receipt = await tools.execute(
        ToolExecutionRequest(
            request_id=str(uuid4()),
            operation_id=lease.operation_id,
            tenant_id="tenant-a",
            tool_id="repo.read",
            idempotency_key="engine-tool-meter",
            arguments={"path": "README.md"},
            requested_at=_now(),
        ),
        now=_now(),
    )

    assert receipt.status is ToolExecutionStatus.SUCCEEDED
    active = ledger.snapshot("tenant-a")
    assert active["active_reservations"] == 1
    assert active["metered_by_category"]["tool"]["tool_calls"] == 1

    completion = service.complete_execution_admission(
        command.execution_request.execution_id,
        now=_now() + timedelta(seconds=1),
    )
    assert completion is not None
    closed = ledger.snapshot("tenant-a")
    assert closed["active_reservations"] == 0
    assert closed["committed"]["tool_calls"] == 1
    assert closed["committed"]["operations"] == 1

def test_submit_meters_execution_and_submission_storage_without_replay_double_count(
    tmp_path,
) -> None:
    service, _runtime, ledger = _admitted_service(tmp_path)
    command = _command()

    first = service.submit(
        command,
        verified_service_principal="backend-service",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now(),
    )
    first_snapshot = ledger.snapshot("tenant-a")
    storage = first_snapshot["metered_by_category"]["storage"]

    assert first.execution_id == command.execution_request.execution_id
    assert storage["storage_bytes"] > 0
    assert storage["artifact_bytes"] == 0
    assert first_snapshot["usage_events"] == 2

    replay = service.submit(
        command,
        verified_service_principal="backend-service",
        actor_id="actor-a",
        tenant_id="tenant-a",
        now=_now() + timedelta(seconds=1),
    )
    replay_snapshot = ledger.snapshot("tenant-a")

    assert replay == first
    assert replay_snapshot["usage_events"] == 2
    assert (
        replay_snapshot["metered_by_category"]["storage"]["storage_bytes"]
        == storage["storage_bytes"]
    )

def test_external_storage_admission_is_replay_safe_and_tenant_scoped(
    tmp_path,
) -> None:
    service, _runtime, ledger = _admitted_service(tmp_path)

    first = service.consume_external_storage_write(
        verified_service_principal="backend-service",
        tenant_id="tenant-a",
        capability="conversation-persistence",
        resource_id="conversation-message",
        write_id="thread-a:idem-1",
        storage_bytes=128,
        now=_now(),
    )
    replay = service.consume_external_storage_write(
        verified_service_principal="backend-service",
        tenant_id="tenant-a",
        capability="conversation-persistence",
        resource_id="conversation-message",
        write_id="thread-a:idem-1",
        storage_bytes=128,
        now=_now() + timedelta(seconds=1),
    )

    assert first.replayed is False
    assert replay.replayed is True
    assert replay.operation_id == first.operation_id
    assert replay.receipt_id == first.receipt_id
    snapshot = ledger.snapshot("tenant-a")
    assert snapshot["committed"]["storage_bytes"] == 128
    assert snapshot["usage_events"] == 1

    with pytest.raises(
        EngineServiceError,
        match="external storage admission identity conflict",
    ):
        service.consume_external_storage_write(
            verified_service_principal="backend-service",
            tenant_id="tenant-a",
            capability="conversation-persistence",
            resource_id="conversation-message",
            write_id="thread-a:idem-1",
            storage_bytes=129,
            now=_now() + timedelta(seconds=2),
        )

    with pytest.raises(EngineAuthorityError, match="tenant denied"):
        service.consume_external_storage_write(
            verified_service_principal="backend-service",
            tenant_id="tenant-b",
            capability="conversation-persistence",
            resource_id="conversation-message",
            write_id="thread-b:idem-1",
            storage_bytes=64,
            now=_now(),
        )


def test_external_storage_admission_requires_dedicated_scope(tmp_path) -> None:
    service, _runtime, _ledger = _admitted_service(tmp_path)
    service.authorities = _registry(
        scopes=(
            "engine:submit",
            "engine:read",
            "engine:cancel",
            "engine:events",
            "engine:approve",
        )
    )

    with pytest.raises(EngineAuthorityError, match="admission scope denied"):
        service.consume_external_storage_write(
            verified_service_principal="backend-service",
            tenant_id="tenant-a",
            capability="conversation-persistence",
            resource_id="conversation-message",
            write_id="thread-a:idem-scope",
            storage_bytes=64,
            now=_now(),
        )

def test_external_governance_write_registers_replays_and_reconciles(
    tmp_path,
) -> None:
    service, _runtime, _ledger = _admitted_service(tmp_path)
    lifecycle = DataLifecycleRegistry(tmp_path / "governance.sqlite3")
    service.governance_registry = GovernanceRegistry(lifecycle)
    service.authorities = _registry(
        scopes=(
            "engine:submit",
            "engine:read",
            "engine:cancel",
            "engine:events",
            "engine:approve",
            "engine:admission",
            "engine:governance",
        )
    )

    first = service.reconcile_external_governed_write(
        verified_service_principal="backend-service",
        mode="register",
        plane="conversation",
        record_id="message-1",
        tenant_id="tenant-a",
        source_ref="conversation-message://thread-1/message-1",
        data_class="internal",
        purposes=("model-inference", "retrieval-synthesis"),
        deletion_targets=("conversation",),
        created_at=100.0,
        retention_until=200.0,
        exportable=True,
    )
    replay = service.reconcile_external_governed_write(
        verified_service_principal="backend-service",
        mode="register",
        plane="conversation",
        record_id="message-1",
        tenant_id="tenant-a",
        source_ref="conversation-message://thread-1/message-1",
        data_class="internal",
        purposes=("model-inference", "retrieval-synthesis"),
        deletion_targets=("conversation",),
        created_at=100.0,
        retention_until=200.0,
        exportable=True,
    )
    reconciled = service.reconcile_external_governed_write(
        verified_service_principal="backend-service",
        mode="reconcile",
        plane="conversation",
        record_id="message-1",
        tenant_id="tenant-a",
        source_ref="conversation-message://thread-1/message-1",
        data_class="confidential",
        purposes=("model-inference", "retrieval-synthesis"),
        deletion_targets=("conversation",),
        created_at=100.0,
        retention_until=300.0,
        exportable=True,
    )

    assert first.as_dict() == replay.as_dict()
    assert first.record["owner_plane"] == "conversation"
    assert first.record["state"] == "active"
    assert reconciled.record["data_class"] == "confidential"
    assert reconciled.record["retention_until"] == 300.0
    assert lifecycle.get("message-1") == reconciled.record
    lifecycle.close()


def test_external_governance_write_requires_dedicated_scope(tmp_path) -> None:
    service, _runtime, _ledger = _admitted_service(tmp_path)
    lifecycle = DataLifecycleRegistry(tmp_path / "governance-scope.sqlite3")
    service.governance_registry = GovernanceRegistry(lifecycle)
    service.authorities = _registry(
        scopes=(
            "engine:submit",
            "engine:read",
            "engine:cancel",
            "engine:events",
            "engine:approve",
            "engine:admission",
        )
    )

    with pytest.raises(
        EngineAuthorityError,
        match="governance scope denied",
    ):
        service.reconcile_external_governed_write(
            verified_service_principal="backend-service",
            mode="register",
            plane="conversation",
            record_id="message-scope",
            tenant_id="tenant-a",
            source_ref="conversation-message://thread/message-scope",
            data_class="internal",
            purposes=("model-inference",),
        )
    lifecycle.close()


def test_external_governance_write_rejects_cross_tenant_and_bad_lists(
    tmp_path,
) -> None:
    service, _runtime, _ledger = _admitted_service(tmp_path)
    lifecycle = DataLifecycleRegistry(tmp_path / "governance-bounds.sqlite3")
    service.governance_registry = GovernanceRegistry(lifecycle)
    service.authorities = _registry(
        scopes=(
            "engine:submit",
            "engine:read",
            "engine:cancel",
            "engine:events",
            "engine:approve",
            "engine:admission",
            "engine:governance",
        )
    )

    with pytest.raises(EngineAuthorityError, match="tenant denied"):
        service.reconcile_external_governed_write(
            verified_service_principal="backend-service",
            mode="register",
            plane="memory",
            record_id="memory-1",
            tenant_id="tenant-b",
            source_ref="memory://assistant/memory-1",
            data_class="internal",
            purposes=("model-inference",),
        )

    with pytest.raises(EngineServiceError, match="purposes"):
        service.reconcile_external_governed_write(
            verified_service_principal="backend-service",
            mode="register",
            plane="memory",
            record_id="memory-2",
            tenant_id="tenant-a",
            source_ref="memory://assistant/memory-2",
            data_class="internal",
            purposes=(),
        )
    lifecycle.close()

def _governed_service(tmp_path):
    lifecycle = DataLifecycleRegistry()
    governance = GovernanceRegistry(lifecycle)
    service = EngineExecutionService(
        SQLiteExecutionRepository(
            tmp_path / "execution-governed.sqlite3"
        ),
        SQLiteEngineSubmissionStore(
            tmp_path / "submissions-governed.sqlite3"
        ),
        _registry(
            scopes=(
                "engine:submit",
                "engine:read",
                "engine:governance",
            )
        ),
        governance_registry=governance,
    )
    return service, governance


class _RecordingDeletionAdapter:
    def __init__(self) -> None:
        self.deleted = []

    async def delete(self, action) -> None:
        self.deleted.append((action.record_id, action.target))


@pytest.mark.asyncio
async def test_external_governance_engine_execution_skips_conversation_owner(
    tmp_path,
) -> None:
    lifecycle = DataLifecycleRegistry()
    governance = GovernanceRegistry(lifecycle)
    adapters = LifecycleAdapterRegistry()
    memory_adapter = _RecordingDeletionAdapter()
    adapters.register_deletion("memory", memory_adapter)
    executor = LifecycleExecutor(lifecycle, adapters)
    service = EngineExecutionService(
        SQLiteExecutionRepository(tmp_path / "execution-linked.sqlite3"),
        SQLiteEngineSubmissionStore(tmp_path / "submissions-linked.sqlite3"),
        _registry(
            scopes=(
                "engine:submit",
                "engine:read",
                "engine:governance",
            )
        ),
        governance_registry=governance,
        governance_lifecycle_executor=executor,
    )
    governance.register_canonical_write(
        "conversation",
        record_id="thread-linked",
        tenant_id="tenant-a",
        source_ref="conversation-thread://thread-linked",
        data_class="confidential",
        purposes=("model-inference",),
        deletion_targets=("conversation",),
        created_at=10.0,
    )
    governance.register_canonical_write(
        "memory",
        record_id="memory-linked",
        tenant_id="tenant-a",
        source_ref="memory://assistant/memory-linked",
        data_class="confidential",
        purposes=("assistant-memory",),
        deletion_targets=("memory",),
        created_at=10.0,
    )
    plan = service.request_external_governance_deletion(
        verified_service_principal="backend-service",
        tenant_id="tenant-a",
        record_ids=("thread-linked", "memory-linked"),
    )

    result = await service.execute_external_governance_engine_targets(
        verified_service_principal="backend-service",
        tenant_id="tenant-a",
        plan_id=plan["plan_id"],
    )

    assert result["executed_targets"] == ["memory"]
    assert memory_adapter.deleted == [("memory-linked", "memory")]
    pending = lifecycle.pending_deletion_plan(
        plan["plan_id"],
        tenant_id="tenant-a",
    )
    assert [
        (action.record_id, action.target)
        for action in pending.actions
    ] == [("thread-linked", "conversation")]


def test_external_governance_deletion_plan_ack_and_inventory_are_tenant_fenced(
    tmp_path,
) -> None:
    service, governance = _governed_service(tmp_path)
    for record_id in ("thread-1", "message-1"):
        governance.register_canonical_write(
            "conversation",
            record_id=record_id,
            tenant_id="tenant-a",
            source_ref=(
                "conversation-thread://thread-1"
                if record_id == "thread-1"
                else "conversation-message://thread-1/message-1"
            ),
            data_class="confidential",
            purposes=("model-inference",),
            deletion_targets=("conversation",),
            created_at=10.0,
            exportable=True,
        )

    inventory = service.external_governance_inventory(
        verified_service_principal="backend-service",
        tenant_id="tenant-a",
    )
    assert inventory["tenant_id"] == "tenant-a"
    assert inventory["count"] == 2
    assert {row["record_id"] for row in inventory["records"]} == {
        "thread-1",
        "message-1",
    }

    plan = service.request_external_governance_deletion(
        verified_service_principal="backend-service",
        tenant_id="tenant-a",
        record_ids=("thread-1", "message-1"),
        reason="tenant-request",
        now=_now(),
    )
    assert plan["tenant_id"] == "tenant-a"
    assert {row["record_id"] for row in plan["actions"]} == {
        "thread-1",
        "message-1",
    }
    assert {row["target"] for row in plan["actions"]} == {
        "conversation",
    }

    for row in plan["actions"]:
        receipt = service.acknowledge_external_governance_deletion(
            verified_service_principal="backend-service",
            tenant_id="tenant-a",
            plan_id=plan["plan_id"],
            record_id=row["record_id"],
            target=row["target"],
            now=_now() + timedelta(seconds=1),
        )
        assert receipt["record_id"] == row["record_id"]
        assert receipt["target"] == "conversation"
        assert receipt["state"] == "deleted"

    assert governance.lifecycle.get("thread-1")["state"] == "deleted"
    assert governance.lifecycle.get("message-1")["state"] == "deleted"


def test_external_governance_lifecycle_requires_governance_scope(tmp_path) -> None:
    lifecycle = DataLifecycleRegistry()
    governance = GovernanceRegistry(lifecycle)
    governance.register_canonical_write(
        "conversation",
        record_id="thread-denied",
        tenant_id="tenant-a",
        source_ref="conversation-thread://thread-denied",
        data_class="confidential",
        purposes=("model-inference",),
        deletion_targets=("conversation",),
        created_at=10.0,
    )
    service = EngineExecutionService(
        SQLiteExecutionRepository(tmp_path / "execution-denied.sqlite3"),
        SQLiteEngineSubmissionStore(
            tmp_path / "submissions-denied.sqlite3"
        ),
        _registry(scopes=("engine:read",)),
        governance_registry=governance,
    )

    with pytest.raises(
        EngineAuthorityError,
        match="governance scope denied",
    ):
        service.request_external_governance_deletion(
            verified_service_principal="backend-service",
            tenant_id="tenant-a",
            record_ids=("thread-denied",),
        )
