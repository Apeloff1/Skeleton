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
from skeleton.api.engine_routes import (
    _engine_coordinator,
    _engine_service,
    _engine_service_token,
    router,
)
from skeleton.api.engine_service import (
    EngineContextHandoff,
    EngineExecutionCommand,
    EngineExecutionService,
    SQLiteEngineSubmissionStore,
)
from skeleton.contracts.ai_execution import AIExecutionRequest
from skeleton.config.settings import EngineSettings
from skeleton.contracts.operation import OperationEnvelope
from skeleton.persistence.execution_repository import SQLiteExecutionRepository


_SERVICE_TOKEN = "test-engine-service-token-" + ("x" * 32)


def _now() -> datetime:
    return datetime.now(timezone.utc)


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
    handoff = EngineContextHandoff(
        operation_id=operation.operation_id,
        execution_id="route-exec",
        turn_id="route-turn",
        tenant_id="tenant-a",
        context_id="route-context",
        context_digest="a" * 64,
        compiler_version="test-compiler",
        source_snapshot=(("route-segment", "b" * 64),),
        data_class="internal",
        instructions="Follow canonical policy.",
        prompt="Answer the route request.",
    )
    execution_request = AIExecutionRequest(
        operation_id=operation.operation_id,
        execution_id="route-exec",
        objective="Answer the route request.",
        context_policy={
            "tenant_id": "tenant-a",
            "capability": "assistant.chat",
            "data_class": "internal",
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
        compiled_context=handoff,
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
    app.dependency_overrides[_engine_service_token] = lambda: _SERVICE_TOKEN
    app.dependency_overrides[_engine_coordinator] = lambda: None
    return TestClient(app)


def test_engine_service_token_is_masked_in_settings_repr() -> None:
    settings = EngineSettings(service_token=_SERVICE_TOKEN)

    assert _SERVICE_TOKEN not in repr(settings)
    assert settings.service_token.get_secret_value() == _SERVICE_TOKEN


def test_engine_routes_require_verified_service_principal_and_round_trip(tmp_path) -> None:
    service, command = _service_and_command(tmp_path)
    client = _client(service)

    missing = client.post(
        "/api/v1/engine/executions",
        json={
            "actor_id": "actor-a",
            "tenant_id": "tenant-a",
            "command": command.as_dict(),
        },
    )
    assert missing.status_code == 401

    spoofed_principal = client.post(
        "/api/v1/engine/executions",
        json={
            "actor_id": "actor-a",
            "tenant_id": "tenant-a",
            "command": command.as_dict(),
        },
        headers={"x-zaibatsu-attester": "backend-service"},
    )
    assert spoofed_principal.status_code == 401

    bad_token = client.post(
        "/api/v1/engine/executions",
        json={
            "actor_id": "actor-a",
            "tenant_id": "tenant-a",
            "command": command.as_dict(),
        },
        headers={
            "x-zaibatsu-attester": "backend-service",
            "authorization": "Bearer " + ("z" * 40),
        },
    )
    assert bad_token.status_code == 401

    headers = {
        "x-zaibatsu-attester": "backend-service",
        "authorization": "Bearer " + _SERVICE_TOKEN,
    }
    submitted = client.post(
        "/api/v1/engine/executions",
        json={
            "actor_id": "actor-a",
            "tenant_id": "tenant-a",
            "command": command.as_dict(),
        },
        headers=headers,
    )
    assert submitted.status_code == 202
    assert submitted.json()["execution_id"] == "route-exec"

    replay = client.post(
        "/api/v1/engine/executions",
        json={
            "actor_id": "actor-a",
            "tenant_id": "tenant-a",
            "command": command.as_dict(),
        },
        headers=headers,
    )
    assert replay.status_code == 202
    assert replay.json() == submitted.json()

    status = client.get(
        (
            "/api/v1/engine/executions/route-exec"
            "?actor_id=actor-a&tenant_id=tenant-a"
        ),
        headers=headers,
    )
    assert status.status_code == 200
    assert status.json()["execution_state"] == "created"

    events = client.get(
        (
            "/api/v1/engine/executions/route-exec/events"
            "?actor_id=actor-a&tenant_id=tenant-a"
        ),
        headers=headers,
    )
    assert events.status_code == 200
    assert events.json()["events"][0]["type"] == "execution.state"

    cancelled = client.post(
        "/api/v1/engine/executions/route-exec/cancel",
        json={
            "actor_id": "actor-a",
            "tenant_id": "tenant-a",
            "reason": "user requested cancellation",
        },
        headers=headers,
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["cancellation_requested"] is True



def test_engine_routes_reject_cross_actor_execution_access(tmp_path) -> None:
    service, command = _service_and_command(tmp_path)
    client = _client(service)
    headers = {
        "x-zaibatsu-attester": "backend-service",
        "authorization": "Bearer " + _SERVICE_TOKEN,
    }
    submitted = client.post(
        "/api/v1/engine/executions",
        json={
            "actor_id": "actor-a",
            "tenant_id": "tenant-a",
            "command": command.as_dict(),
        },
        headers=headers,
    )
    assert submitted.status_code == 202

    wrong_status = client.get(
        (
            "/api/v1/engine/executions/route-exec"
            "?actor_id=actor-b&tenant_id=tenant-a"
        ),
        headers=headers,
    )
    assert wrong_status.status_code == 422

    wrong_events = client.get(
        (
            "/api/v1/engine/executions/route-exec/events"
            "?actor_id=actor-b&tenant_id=tenant-a"
        ),
        headers=headers,
    )
    assert wrong_events.status_code == 422

    wrong_cancel = client.post(
        "/api/v1/engine/executions/route-exec/cancel",
        json={
            "actor_id": "actor-b",
            "tenant_id": "tenant-a",
            "reason": "wrong actor",
        },
        headers=headers,
    )
    assert wrong_cancel.status_code == 422
