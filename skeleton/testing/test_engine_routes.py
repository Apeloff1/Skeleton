from __future__ import annotations

from skeleton.config.settings import EngineSettings
from skeleton.testing.engine_route_test_support import (
    _SERVICE_TOKEN,
    _inventory_headers,
    _now,
    _service_and_command,
    _client,
)


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
    assert wrong_status.status_code == 403

    wrong_events = client.get(
        (
            "/api/v1/engine/executions/route-exec/events"
            "?actor_id=actor-b&tenant_id=tenant-a"
        ),
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
