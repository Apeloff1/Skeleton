"""The actual engine status route binds local selection without exposing secrets."""
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from skeleton.api import engine_routes
from skeleton.api.engine_authority import EngineAuthorityRegistry, EngineServiceGrant

TOKEN = "engine-status-fixture-" + "x" * 40


def _client(*, scopes=frozenset({"engine:read"})):
    app = FastAPI()
    app.include_router(engine_routes.router, prefix="/api/v1")
    authorities = EngineAuthorityRegistry([EngineServiceGrant(
        service_principal="status-backend", scopes=scopes,
        tenant_ids=frozenset({"tenant-status"}),
        capabilities=frozenset({"assistant.chat"}),
    )])
    registry = SimpleNamespace(active_id="local", available=True, statuses=lambda: [{
        "id": "local", "model": "fixture-native", "available": True,
        "execution_mode": "local", "network_policy": "none",
        "api_key": "must-never-leak", "base_url": "private-provider-url",
        "artifact": {"model_digest": "a" * 64, "path": "/private/checkpoint"},
    }])
    app.dependency_overrides[engine_routes._engine_service] = lambda: SimpleNamespace(authorities=authorities)
    app.dependency_overrides[engine_routes._engine_service_token] = lambda: TOKEN
    app.dependency_overrides[engine_routes._engine_coordinator] = lambda: SimpleNamespace(provider_registry=registry)
    return TestClient(app)


def test_authenticated_read_returns_actual_local_mode_and_sanitized_identity():
    response = _client().get("/api/v1/engine/providers", headers={
        "Authorization": "Bearer " + TOKEN, "x-zaibatsu-attester": "status-backend",
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload["active"] == "local" and payload["available"] is True
    assert payload["providers"][0]["execution_mode"] == "local"
    assert payload["providers"][0]["network_policy"] == "none"
    assert payload["providers"][0]["artifact"] == {"model_digest": "a" * 64}
    assert "must-never-leak" not in response.text
    assert "/private/checkpoint" not in response.text


@pytest.mark.parametrize("headers,status", [
    ({}, 401),
    ({"Authorization": "Bearer wrong", "x-zaibatsu-attester": "status-backend"}, 401),
    ({"Authorization": "Bearer " + TOKEN, "x-zaibatsu-attester": "unknown"}, 403),
])
def test_status_requires_authenticated_declared_service(headers, status):
    assert _client().get("/api/v1/engine/providers", headers=headers).status_code == status


def test_status_requires_read_scope():
    response = _client(scopes=frozenset({"engine:submit"})).get("/api/v1/engine/providers", headers={
        "Authorization": "Bearer " + TOKEN, "x-zaibatsu-attester": "status-backend",
    })
    assert response.status_code == 403
