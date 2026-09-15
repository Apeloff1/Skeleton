"""Contract tests for API/CLI command parity and error/auth semantics."""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import HTTPException

from skeleton.__main__ import main
from skeleton.api import command_routes
from skeleton.application import CommandService, build_runtime_command_service, parity_matrix


class _FakeState:
    genesis = None
    memory_trinity = None
    registry = None
    gameforge = None

    def is_healthy(self):
        return {"overall": True, "checks": {"fake": {"status": "ok"}}}


def test_parity_matrix_maps_all_required_operation_families():
    matrix = parity_matrix()
    rows = {row["name"]: row for row in matrix["commands"]}
    assert set(rows) == {"run", "tool", "memory", "status", "configuration", "admin"}
    assert matrix["full_surface_parity"] is True
    assert all(row["api"] and row["cli"] for row in rows.values())
    assert {name for name, row in rows.items() if row["auth_required"]} == {
        "run",
        "tool",
        "memory",
        "admin",
    }


def test_unknown_command_has_stable_cli_and_http_semantics():
    result = CommandService().execute("does-not-exist")
    assert result.ok is False
    assert result.exit_code == 2
    assert result.http_status == 404
    assert result.to_payload()["error"]["code"] == "invalid_command"


def test_contracted_command_without_handler_is_explicitly_unsupported():
    result = CommandService().execute("run")
    assert result.ok is False
    assert result.exit_code == 3
    assert result.http_status == 501
    assert result.to_payload()["error"]["code"] == "unsupported_operation"


def test_runtime_status_and_configuration_share_one_result_shape():
    service = build_runtime_command_service(_FakeState())
    status = service.execute("status")
    config = service.execute("configuration")

    assert status.ok is True
    assert status.data["status"] == "healthy"
    assert status.data["initialized"] is False
    assert config.ok is True
    assert config.data["application"] == "Skeleton"
    assert config.data["runtime_initialized"] is False


def test_uninitialized_runtime_returns_normalized_unavailable_error():
    result = build_runtime_command_service(_FakeState()).execute("memory", {"query": "hello"})
    assert result.ok is False
    assert result.exit_code == 3
    assert result.http_status == 503
    assert result.to_payload()["error"]["code"] == "unavailable"


def test_cli_status_uses_shared_contract(capsys):
    exit_code = main(["status"])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["command"] == "status"
    assert payload["ok"] is True
    assert payload["contract_version"] == parity_matrix()["contract_version"]


def test_api_status_uses_shared_contract_without_seal(monkeypatch):
    def unexpected_seal(_value):
        raise AssertionError("public status command must not require a seal")

    monkeypatch.setattr(command_routes, "require_seal", unexpected_seal)
    response = asyncio.run(
        command_routes.execute_command("status", {}, state=_FakeState(), x_gf_seal=None)
    )
    assert response["command"] == "status"
    assert response["ok"] is True
    assert response["data"]["status"] == "healthy"


@pytest.mark.parametrize("command", ["run", "tool", "memory", "admin"])
def test_api_auth_required_commands_reject_missing_seal(monkeypatch, command):
    observed = []

    def fake_require_seal(value):
        observed.append(value)
        if value != "valid-seal":
            raise HTTPException(status_code=401, detail="invalid seal")
        return "attester"

    monkeypatch.setattr(command_routes, "require_seal", fake_require_seal)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            command_routes.execute_command(command, {}, state=_FakeState(), x_gf_seal=None)
        )
    assert exc_info.value.status_code == 401
    assert observed == [None]


@pytest.mark.parametrize("command", ["run", "tool", "memory", "admin"])
def test_api_auth_required_commands_accept_valid_seal_before_dispatch(monkeypatch, command):
    observed = []

    def fake_require_seal(value):
        observed.append(value)
        if value != "valid-seal":
            raise HTTPException(status_code=401, detail="invalid seal")
        return "attester"

    monkeypatch.setattr(command_routes, "require_seal", fake_require_seal)
    response = asyncio.run(
        command_routes.execute_command(
            command,
            {},
            state=_FakeState(),
            x_gf_seal="valid-seal",
        )
    )

    assert observed == ["valid-seal"]
    if command == "admin":
        assert response["ok"] is True
        assert response["data"]["initialized"] is False
    else:
        assert response.status_code == 503
        payload = json.loads(response.body)
        assert payload["error"]["code"] == "unavailable"
