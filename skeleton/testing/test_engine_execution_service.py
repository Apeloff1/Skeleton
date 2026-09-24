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
    EngineSubmissionConflict,
    SQLiteEngineSubmissionStore,
)
from skeleton.contracts.ai_execution import (
    AIExecutionRequest,
    AgentTurn,
    ExecutionState,
)
from skeleton.contracts.operation import OperationEnvelope
from skeleton.persistence.execution_repository import SQLiteExecutionRepository


def _now() -> datetime:
    return datetime(2026, 9, 23, 20, 0, tzinfo=timezone.utc)


def _operation(
    *,
    operation_id: str | None = None,
    tenant_id: str = "tenant-a",
    actor_id: str = "actor-a",
    capability: str = "assistant.chat",
    idempotency_key: str = "idem-1",
) -> OperationEnvelope:
    return OperationEnvelope(
        operation_id=operation_id or str(uuid4()),
        tenant_id=tenant_id,
        actor_id=actor_id,
        capability=capability,
        created_at=_now(),
        deadline=_now() + timedelta(minutes=10),
        idempotency_key=idempotency_key,
        trace_id="trace-1",
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
        created_at=_now(),
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
    ),
    expires_at: datetime | None = None,
) -> DelegatedAuthority:
    return DelegatedAuthority(
        service_principal=service_principal,
        actor_id=operation.actor_id,
        tenant_id=operation.tenant_id,
        scopes=tuple(scopes),
        capability=operation.capability,
        issued_at=_now(),
        expires_at=expires_at or (_now() + timedelta(minutes=5)),
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


def test_submit_is_idempotent_and_ack_survives_service_restart(tmp_path) -> None:
    command = _command()
    service = _service(tmp_path)

    first = service.submit(
        command,
        verified_service_principal="backend-service",
        now=_now(),
    )

    restarted = _service(tmp_path)
    replay = restarted.submit(
        command,
        verified_service_principal="backend-service",
        now=_now() + timedelta(seconds=30),
    )

    assert replay == first
    assert first.execution_id == "exec-1"
    assert first.state == "admitted"
    assert first.status_ref.endswith("/exec-1")
    assert first.events_ref.endswith("/exec-1/events")


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
        now=_now(),
    )

    status = service.status(
        "exec-1",
        verified_service_principal="backend-service",
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
        now=_now(),
    )

    first = service.cancel(
        "exec-1",
        verified_service_principal="backend-service",
        now=_now(),
    )
    second = service.cancel(
        "exec-1",
        verified_service_principal="backend-service",
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
