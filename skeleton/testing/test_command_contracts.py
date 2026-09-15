"""Contract tests for API/CLI command parity and error semantics."""

from __future__ import annotations

import asyncio
import json

from skeleton.__main__ import main
from skeleton.api.command_routes import execute_command
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


def test_api_status_uses_shared_contract():
    response = asyncio.run(execute_command("status", {}, state=_FakeState()))
    assert response["command"] == "status"
    assert response["ok"] is True
    assert response["data"]["status"] == "healthy"
