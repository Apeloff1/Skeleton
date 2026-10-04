from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
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
from skeleton.config.settings import EngineSettings
from skeleton.contracts.ai_execution import AIExecutionRequest
from skeleton.contracts.operation import OperationEnvelope
from skeleton.persistence.execution_repository import SQLiteExecutionRepository
from skeleton.provider_contract import ProviderArchitectureError
from skeleton.provider_runtime import OpenAIProviderAdapter, ProviderRegistry

_SERVICE_TOKEN = "test-engine-service-token-" + ("x" * 32)


def _now() -> datetime:
    return datetime.now(UTC)


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
            "source_snapshot": [[segment_id, digest] for segment_id, digest in handoff.source_snapshot],
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


def _inventory_registry(*, architecture_loader=None, active="openai"):
    adapter = OpenAIProviderAdapter(
        api_key="inventory-test-secret-key",
        model="inventory-model",
        base_url="https://provider.example.invalid/v1",
        client=object(),
    )
    options = {} if architecture_loader is None else {"architecture_loader": architecture_loader}
    return ProviderRegistry((adapter,), active=active, **options)


def _inventory_headers():
    return {
        "x-zaibatsu-attester": "backend-service",
        "authorization": "Bearer " + _SERVICE_TOKEN,
    }


def test_engine_provider_inventory_uses_canonical_redacted_status(tmp_path) -> None:
    service, _command = _service_and_command(tmp_path)
    registry = _inventory_registry()
    client = _client(service)
    client.app.dependency_overrides[_engine_coordinator] = lambda: SimpleNamespace(provider_registry=registry)

    for params in ({}, {"tenant_id": "tenant-a"}):
        response = client.get("/api/v1/engine/providers", headers=_inventory_headers(), params=params)
        assert response.status_code == 200
        assert response.json() == {
            "active": registry.active_id,
            "available": registry.available,
            "providers": registry.statuses(),
        }
        assert response.json()["available"] is True
        assert response.json()["providers"][0]["architecture_acknowledged"] is True
        for secret in (
            _SERVICE_TOKEN,
            "inventory-test-secret-key",
            "provider.example.invalid",
            "api_key",
            "base_url",
        ):
            assert secret not in response.text


@pytest.mark.parametrize(
    ("failure", "expected_status"),
    [
        ("missing_headers", 401),
        ("missing_principal", 401),
        ("invalid_token", 401),
        ("ungranted_principal", 403),
        ("missing_read_scope", 403),
        ("cross_tenant", 403),
    ],
)
def test_engine_provider_inventory_preserves_service_and_tenant_authority(
    tmp_path, failure, expected_status
) -> None:
    service, _command = _service_and_command(tmp_path)
    client = _client(service)
    # Any attempt to inspect this registry before rejecting the request fails.
    client.app.dependency_overrides[_engine_coordinator] = lambda: SimpleNamespace(provider_registry=object())
    headers = _inventory_headers()
    params = {}
    if failure == "missing_headers":
        headers = {}
    elif failure == "missing_principal":
        del headers["x-zaibatsu-attester"]
    elif failure == "invalid_token":
        headers["authorization"] = "Bearer invalid"
    elif failure == "ungranted_principal":
        headers["x-zaibatsu-attester"] = "ungranted-service"
    elif failure == "missing_read_scope":
        service.authorities = EngineAuthorityRegistry(
            [
                EngineServiceGrant(
                    service_principal="backend-service",
                    scopes=frozenset({"engine:submit"}),
                    tenant_ids=frozenset({"tenant-a"}),
                    capabilities=frozenset({"assistant.chat"}),
                )
            ]
        )
    elif failure == "cross_tenant":
        params["tenant_id"] = "tenant-b"
    response = client.get("/api/v1/engine/providers", headers=headers, params=params)
    assert response.status_code == expected_status
    assert _SERVICE_TOKEN not in response.text


@pytest.mark.parametrize("coordinator", [None, SimpleNamespace()])
def test_engine_provider_inventory_missing_runtime_is_unavailable(tmp_path, coordinator) -> None:
    service, _command = _service_and_command(tmp_path)
    client = _client(service)
    client.app.dependency_overrides[_engine_coordinator] = lambda: coordinator
    response = client.get("/api/v1/engine/providers", headers=_inventory_headers())
    assert response.status_code == 503


def test_engine_provider_inventory_acknowledgement_failure_is_redacted_degraded_status(tmp_path) -> None:
    def denied_architecture(_provider_id):
        raise ProviderArchitectureError("sensitive architecture configuration")

    service, _command = _service_and_command(tmp_path)
    registry = _inventory_registry(architecture_loader=denied_architecture)
    client = _client(service)
    client.app.dependency_overrides[_engine_coordinator] = lambda: SimpleNamespace(provider_registry=registry)
    response = client.get("/api/v1/engine/providers", headers=_inventory_headers())
    assert response.status_code == 200
    payload = response.json()
    assert payload["active"] == "openai"
    assert payload["available"] is False
    assert payload["providers"][0]["available"] is False
    assert payload["providers"][0]["architecture_acknowledged"] is False
    assert "sensitive architecture configuration" not in response.text


def test_engine_provider_inventory_unknown_active_provider_is_unavailable(tmp_path) -> None:
    service, _command = _service_and_command(tmp_path)
    registry = _inventory_registry(active="unknown-provider")
    client = _client(service)
    client.app.dependency_overrides[_engine_coordinator] = lambda: SimpleNamespace(provider_registry=registry)
    response = client.get("/api/v1/engine/providers", headers=_inventory_headers())
    assert response.status_code == 503


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
        ("/api/v1/engine/executions/route-exec" "?actor_id=actor-a&tenant_id=tenant-a"),
        headers=headers,
    )
    assert status.status_code == 200
    assert status.json()["execution_state"] == "created"

    events = client.get(
        ("/api/v1/engine/executions/route-exec/events" "?actor_id=actor-a&tenant_id=tenant-a"),
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
        ("/api/v1/engine/executions/route-exec" "?actor_id=actor-b&tenant_id=tenant-a"),
        headers=headers,
    )
    assert wrong_status.status_code == 403

    wrong_events = client.get(
        ("/api/v1/engine/executions/route-exec/events" "?actor_id=actor-b&tenant_id=tenant-a"),
        headers=headers,
    )
    assert wrong_events.status_code == 403

    wrong_cancel = client.post(
        "/api/v1/engine/executions/route-exec/cancel",
        json={
            "actor_id": "actor-b",
            "tenant_id": "tenant-a",
            "reason": "wrong actor",
        },
        headers=headers,
    )
    assert wrong_cancel.status_code == 403
