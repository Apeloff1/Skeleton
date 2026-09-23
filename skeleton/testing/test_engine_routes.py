from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from skeleton.api.engine_authority import (
    DelegatedAuthority,
    EngineAuthorityRegistry,
    EngineServiceGrant,
    engine_request_binding,
)
from skeleton.api.engine_routes import _engine_service, router
from skeleton.api.engine_service import (
    EngineExecutionCommand,
    EngineExecutionService,
    SQLiteEngineSubmissionStore,
)
from skeleton.contracts.ai_execution import AIExecutionRequest
from skeleton.contracts.operation import OperationEnvelope
from skeleton.persistence.execution_repository import SQLiteExecutionRepository


def _now() -> datetime:
    return datetime(2026, 9, 23, 20, 15, tzinfo=timezone.utc)


def _service_and_command(tmp_path):
    operation = OperationEnvelope(
        operation_id=str(uuid4()),
        tenant_id="tenant-a",
        actor_id="actor-a",
        capability="assistant.chat",
        created_at=_now(),
        deadline=_now() + timedelta(minutes=10),
        idempotency_key="route-idem",
        trace_id="trace-route",
    )
    execution_request = AIExecutionRequest(
        operation_id=operation.operation_id,
        execution_id="route-exec",
        objective="Answer the route request.",
        context_policy={
            "tenant_id": "tenant-a",
            "capability": "assistant.chat",
            "data_class": "internal",
        },
        tool_policy={
            "tenant_id": "tenant-a",
            "allowed_tool_ids": [],
        },
        resource_budget={
            "max_model_turns": 4,
            "max_tool_calls": 4,
        },
        stop_policy={"max_repeat_tool_batches": 1},
        created_at=_now(),
    )
    authority = DelegatedAuthority(
        service_principal="backend-service",
        actor_id="actor-a",
        tenant_id="tenant-a",
        scopes=(
            "engine:submit",
            "engine:read",
            "engine:cancel",
            "engine:events",
        ),
        capability="assistant.chat",
        issued_at=_now(),
        expires_at=_now() + timedelta(minutes=5),
        request_binding=engine_request_binding(
            operation,
            execution_request,
        ),
    )
    command = EngineExecutionCommand(
        operation=operation,
        execution_request=execution_request,
        delegated_authority=authority,
        context_seed_refs=("conversation:route-thread",),
        resource_budget=dict(execution_request.resource_budget),
        stream_preferences={"mode": "events"},
    )
    registry = EngineAuthorityRegistry(
        [
            EngineServiceGrant(
                service_principal="backend-service",
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
    service = EngineExecutionService(
        SQLiteExecutionRepository(tmp_path / "execution.sqlite3"),
        SQLiteEngineSubmissionStore(tmp_path / "submission.sqlite3"),
        registry,
    )
    return service, command


def _client(service: EngineExecutionService) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[_engine_service] = lambda: service
    return TestClient(app)


def test_engine_routes_require_verified_service_principal_and_round_trip(tmp_path) -> None:
    service, command = _service_and_command(tmp_path)
    client = _client(service)

    missing = client.post(
        "/api/v1/engine/executions",
        json={"command": command.as_dict()},
    )
    assert missing.status_code == 401

    headers = {"x-zaibatsu-attester": "backend-service"}
    submitted = client.post(
        "/api/v1/engine/executions",
        json={"command": command.as_dict()},
        headers=headers,
    )
    assert submitted.status_code == 202
    assert submitted.json()["execution_id"] == "route-exec"

    replay = client.post(
        "/api/v1/engine/executions",
        json={"command": command.as_dict()},
        headers=headers,
    )
    assert replay.status_code == 202
    assert replay.json() == submitted.json()

    status = client.get(
        "/api/v1/engine/executions/route-exec",
        headers=headers,
    )
    assert status.status_code == 200
    assert status.json()["execution_state"] == "created"

    events = client.get(
        "/api/v1/engine/executions/route-exec/events",
        headers=headers,
    )
    assert events.status_code == 200
    assert events.json()["events"][0]["type"] == "execution.state"

    cancelled = client.post(
        "/api/v1/engine/executions/route-exec/cancel",
        json={"reason": "user requested cancellation"},
        headers=headers,
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["cancellation_requested"] is True
