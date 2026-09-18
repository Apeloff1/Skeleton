"""Regression coverage for F-52..F-59 import-free audits."""

from __future__ import annotations

import json

import pytest

from skeleton.__main__ import main
from skeleton.application import (
    ALLOW_LIST_AUDIT_KIND,
    AUTHZ_AUDIT_KIND,
    CAPABILITY_MANIFEST_VERSION,
    DEV_TOKEN_AUDIT_KIND,
    GATE_STACK_AUDIT_KIND,
    OPEN_DEV_AUDIT_KIND,
    VERSION_AUDIT_KIND,
    allow_list_audit_snapshot,
    authz_audit_snapshot,
    capability_manifest,
    dev_token_audit_snapshot,
    gate_stack_audit_snapshot,
    get_allow_list_audit_row,
    get_authz_audit_row,
    get_dev_token_audit_row,
    get_gate_stack_audit_row,
    get_open_dev_audit_row,
    get_version_audit_row,
    open_dev_audit_snapshot,
    version_audit_snapshot,
)


def _assert_import_free(monkeypatch, snapshot, kind: str) -> None:
    called = False

    def should_not_import(_module_name: str):
        nonlocal called
        called = True
        raise AssertionError("audit must not import capability modules")

    monkeypatch.setattr("skeleton.application.capability_runtime.import_module", should_not_import)
    payload = snapshot()
    assert called is False
    assert payload["schema_version"] == CAPABILITY_MANIFEST_VERSION == 1
    assert payload["kind"] == kind


def _service():
    from skeleton.application import build_runtime_command_service

    class _State:
        genesis = None

        def is_healthy(self):
            return {"overall": True}

    return build_runtime_command_service(_State())


def test_gate_stack_audit_locks_headerbound_outermost(monkeypatch) -> None:
    _assert_import_free(monkeypatch, gate_stack_audit_snapshot, GATE_STACK_AUDIT_KIND)
    payload = gate_stack_audit_snapshot()
    assert payload["inner_first"] == [
        "PolicyGateMiddleware",
        "AuthMiddleware",
        "WormAuditMiddleware",
        "BodyBoundMiddleware",
        "WriteAdmitMiddleware",
        "RequestSealMiddleware",
        "HeaderBoundMiddleware",
    ]
    assert payload["outer_first"][0] == "HeaderBoundMiddleware"
    assert payload["outer_first"][-1] == "PolicyGateMiddleware"
    rows = {row["layer"]: row for row in payload["layers"]}
    assert rows["HeaderBoundMiddleware"]["outermost"] is True
    assert rows["PolicyGateMiddleware"]["innermost"] is True


def test_allow_list_audit_locks_target_and_curve_sites(monkeypatch) -> None:
    _assert_import_free(monkeypatch, allow_list_audit_snapshot, ALLOW_LIST_AUDIT_KIND)
    payload = allow_list_audit_snapshot()
    assert payload["targets"] == ["json", "yaml", "godot"]
    assert payload["curves"] == ["linear", "quadratic", "exponential"]
    assert payload["keys"] == [
        "skeleton.api.routes:pipeline_game_logic",
        "skeleton.api.routes:forge_materialise",
        "skeleton.api.routes:forge_archetype",
        "skeleton.api.routes:gameforge_run",
        "skeleton.api.routes:gameforge_intake",
        "skeleton.application.runtime_commands:_run_handler",
    ]
    rows = {row["key"]: row for row in payload["usages"]}
    assert rows["skeleton.api.routes:pipeline_game_logic"]["catalog"] == "PROGRESSION_CURVES"
    assert rows["skeleton.application.runtime_commands:_run_handler"]["catalog"] == "MATERIALISE_TARGETS"


def test_version_audit_locks_16_0_0_identity(monkeypatch) -> None:
    _assert_import_free(monkeypatch, version_audit_snapshot, VERSION_AUDIT_KIND)
    payload = version_audit_snapshot()
    assert payload["values"] == ["16.0.0"]
    assert payload["drift"] == []
    sources = [row["source"] for row in payload["versions"]]
    assert "skeleton:__version__" in sources
    assert "skeleton.api.server:FastAPI.version" in sources


def test_authz_audit_locks_memory_as_sealed_read(monkeypatch) -> None:
    _assert_import_free(monkeypatch, authz_audit_snapshot, AUTHZ_AUDIT_KIND)
    payload = authz_audit_snapshot()
    assert payload["mutating_without_auth"] == []
    assert payload["auth_without_mutating"] == ["memory"]
    rows = {row["command"]: row for row in payload["commands"]}
    assert rows["run"]["mutating"] is True
    assert rows["run"]["auth_required"] is True
    assert rows["status"]["auth_required"] is False


def test_open_dev_audit_locks_no_default_leak(monkeypatch) -> None:
    _assert_import_free(monkeypatch, open_dev_audit_snapshot, OPEN_DEV_AUDIT_KIND)
    payload = open_dev_audit_snapshot()
    assert payload["leaked_into_default"] == []
    assert payload["runtime_root_open"] is True
    assert payload["extras"] == [
        "/cortex/status",
        "/cockpit",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/api/v1/health",
        "/api/v1/metrics",
        "/api/v1/genesis",
    ]
    assert "/api/v1/health/live" in payload["default"]


def test_dev_token_audit_locks_truthy_allow_list(monkeypatch) -> None:
    _assert_import_free(monkeypatch, dev_token_audit_snapshot, DEV_TOKEN_AUDIT_KIND)
    payload = dev_token_audit_snapshot()
    assert payload["names"] == ["1", "true", "yes", "on"]
    assert "false" not in payload["names"]


def test_cli_http_and_command_parity_for_f52_audits(capsys) -> None:
    import asyncio

    from fastapi import HTTPException

    from skeleton.api import routes

    pairs = [
        (["capabilities", "--stack-audit"], gate_stack_audit_snapshot, routes.application_gate_stack_audit, "stack_audit"),
        (["capabilities", "--allow-audit"], allow_list_audit_snapshot, routes.application_allow_list_audit, "allow_audit"),
        (["capabilities", "--version-audit"], version_audit_snapshot, routes.application_version_audit, "version_audit"),
        (["capabilities", "--authz-audit"], authz_audit_snapshot, routes.application_authz_audit, "authz_audit"),
        (["capabilities", "--dev-audit"], open_dev_audit_snapshot, routes.application_open_dev_audit, "dev_audit"),
        (["capabilities", "--token-audit"], dev_token_audit_snapshot, routes.application_dev_token_audit, "token_audit"),
    ]
    service = _service()
    identity = service.execute("capabilities")
    assert identity.to_payload()["data"] == capability_manifest()
    for argv, snapshot, http, flag in pairs:
        assert main(argv) == 0
        payload = snapshot()
        assert json.loads(capsys.readouterr().out) == payload
        assert asyncio.run(http()) == payload
        audit = service.execute("capabilities", {flag: True})
        assert audit.ok is True
        assert audit.to_payload()["data"] == payload
        invalid = service.execute("capabilities", {flag: 1})
        assert invalid.ok is False
        both = service.execute("capabilities", {flag: True, "route_audit": True})
        assert both.ok is False

    assert asyncio.run(routes.application_gate_stack_audit_row("HeaderBoundMiddleware")) == get_gate_stack_audit_row(
        "HeaderBoundMiddleware"
    )
    assert asyncio.run(routes.application_allow_list_audit_row("pipeline_game_logic")) == get_allow_list_audit_row(
        "pipeline_game_logic"
    )
    assert asyncio.run(routes.application_version_audit_row("skeleton:__version__")) == get_version_audit_row(
        "skeleton:__version__"
    )
    assert asyncio.run(routes.application_authz_audit_row("memory")) == get_authz_audit_row("memory")
    assert asyncio.run(routes.application_open_dev_audit_row("docs")) == get_open_dev_audit_row("/docs")
    assert asyncio.run(routes.application_dev_token_audit_row("true")) == get_dev_token_audit_row("true")
    with pytest.raises(HTTPException) as missing:
        asyncio.run(routes.application_dev_token_audit_row("false"))
    assert missing.value.status_code == 404
