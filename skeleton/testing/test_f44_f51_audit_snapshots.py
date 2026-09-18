"""Regression coverage for F-44..F-51 import-free audits."""

from __future__ import annotations

import json

import pytest

from skeleton.__main__ import main
from skeleton.application import (
    ADMIT_WRITE_AUDIT_KIND,
    CAPABILITY_MANIFEST_VERSION,
    CAPABILITY_VIEW_AUDIT_KIND,
    CLI_SHARED_AUDIT_KIND,
    GATE_LIMIT_AUDIT_KIND,
    IDEMPOTENCY_AUDIT_KIND,
    SEAL_AUDIT_KIND,
    admit_write_audit_snapshot,
    capability_manifest,
    capability_view_audit_snapshot,
    cli_shared_audit_snapshot,
    gate_limit_audit_snapshot,
    get_admit_write_audit_row,
    get_capability_view_audit_row,
    get_cli_shared_audit_row,
    get_gate_limit_audit_row,
    get_idempotency_audit_row,
    get_seal_audit_row,
    idempotency_audit_snapshot,
    seal_audit_snapshot,
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


def test_capability_view_audit_locks_runtime_cli_help_parity(monkeypatch) -> None:
    _assert_import_free(monkeypatch, capability_view_audit_snapshot, CAPABILITY_VIEW_AUDIT_KIND)
    payload = capability_view_audit_snapshot()
    assert payload["missing_from_runtime"] == []
    assert payload["missing_from_cli"] == []
    assert payload["missing_from_help"] == []
    assert "env_audit" in payload["runtime"]
    assert "view_audit" in payload["runtime"]
    assert "shared_audit" in payload["cli"]
    rows = {row["flag"]: row for row in payload["flags"]}
    assert rows["env_audit"]["in_help"] is True
    assert rows["view_audit"]["in_runtime"] is True


def test_idempotency_audit_locks_replay_remember_pairs(monkeypatch) -> None:
    _assert_import_free(monkeypatch, idempotency_audit_snapshot, IDEMPOTENCY_AUDIT_KIND)
    payload = idempotency_audit_snapshot()
    assert payload["keys"] == [
        "skeleton.api.routes:forge_materialise",
        "skeleton.api.routes:forge_archetype",
        "skeleton.api.routes:gameforge_run",
        "skeleton.api.routes:gameforge_intake",
        "skeleton.api.gameforge_routes:gameforge_run",
    ]
    assert payload["missing_remember"] == []
    assert payload["missing_replay"] == []
    rows = {row["key"]: row for row in payload["handlers"]}
    assert rows["skeleton.api.routes:forge_materialise"]["replay"] is True
    assert rows["skeleton.api.gameforge_routes:gameforge_run"]["remember"] is True


def test_seal_audit_locks_sidecar_depends_and_command_call(monkeypatch) -> None:
    _assert_import_free(monkeypatch, seal_audit_snapshot, SEAL_AUDIT_KIND)
    payload = seal_audit_snapshot()
    assert payload["depends_seal"] == []
    assert payload["calls_seal"] == ["POST /api/v1/commands/execute/{command}"]
    assert payload["sidecar_depends_seal"] == ["POST /api/v1/gameforge/run"]
    assert payload["hmac_open_and_seal_gated"] == []
    assert payload["charter_gated"] == [
        "POST /api/v1/swarm/submit",
        "POST /api/v1/forge/blueprint",
        "POST /api/v1/forge/materialise",
        "POST /api/v1/forge/archetype",
        "POST /api/v1/gameforge/run",
        "POST /api/v1/gameforge/intake",
    ]
    assert payload["charter_without_explicit_seal"] == payload["charter_gated"]
    rows = {row["key"]: row for row in payload["routes"]}
    assert rows["GET /api/v1/health/live"]["hmac_open"] is True
    assert rows["GET /api/v1/health/live"]["explicit_seal"] is False
    assert rows["POST /api/v1/commands/execute/{command}"]["calls_seal"] is True


def test_admit_write_audit_locks_mutating_methods(monkeypatch) -> None:
    _assert_import_free(monkeypatch, admit_write_audit_snapshot, ADMIT_WRITE_AUDIT_KIND)
    payload = admit_write_audit_snapshot()
    assert payload["mutating"] == ["POST", "PUT", "PATCH", "DELETE"]
    assert payload["uncovered_mutating_live"] == []
    assert payload["unused_mutating_methods"] == ["PATCH"]
    rows = {row["method"]: row for row in payload["methods"]}
    assert rows["POST"]["mutating"] is True
    assert rows["POST"]["live_count"] > 0
    assert rows["GET"]["mutating"] is False
    assert rows["PATCH"]["live_count"] == 0


def test_gate_limit_audit_locks_body_and_header_names(monkeypatch) -> None:
    _assert_import_free(monkeypatch, gate_limit_audit_snapshot, GATE_LIMIT_AUDIT_KIND)
    payload = gate_limit_audit_snapshot()
    assert payload["names"] == [
        "SKELETON_GATE_MAX_HEADER_BYTES",
        "SKELETON_GATE_MAX_HEADER_COUNT",
        "SKELETON_GATE_MAX_BODY_BYTES",
    ]
    rows = {row["name"]: row for row in payload["flags"]}
    assert rows["SKELETON_GATE_MAX_BODY_BYTES"]["module"] == "skeleton.api.middleware"
    assert rows["SKELETON_GATE_MAX_HEADER_BYTES"]["module"] == "skeleton.api.request_bounds"


def test_cli_shared_audit_locks_config_alias(monkeypatch) -> None:
    _assert_import_free(monkeypatch, cli_shared_audit_snapshot, CLI_SHARED_AUDIT_KIND)
    payload = cli_shared_audit_snapshot()
    assert payload["aliases"] == {"config": "configuration"}
    assert payload["missing_from_contract"] == []
    rows = {row["cli"]: row for row in payload["commands"]}
    assert rows["command"]["dispatcher"] is True
    assert rows["status"]["spec"] == "status"
    assert rows["config"]["spec"] == "configuration"
    assert rows["config"]["in_contract"] is True


def test_cli_http_and_command_parity_for_f44_audits(capsys) -> None:
    import asyncio

    from fastapi import HTTPException

    from skeleton.api import routes

    pairs = [
        (["capabilities", "--view-audit"], capability_view_audit_snapshot, routes.application_capability_view_audit, "view_audit"),
        (["capabilities", "--idempotency-audit"], idempotency_audit_snapshot, routes.application_idempotency_audit, "idempotency_audit"),
        (["capabilities", "--seal-audit"], seal_audit_snapshot, routes.application_seal_audit, "seal_audit"),
        (["capabilities", "--admit-audit"], admit_write_audit_snapshot, routes.application_admit_write_audit, "admit_audit"),
        (["capabilities", "--limit-audit"], gate_limit_audit_snapshot, routes.application_gate_limit_audit, "limit_audit"),
        (["capabilities", "--shared-audit"], cli_shared_audit_snapshot, routes.application_cli_shared_audit, "shared_audit"),
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

    row = asyncio.run(routes.application_capability_view_audit_row("env_audit"))
    assert row == get_capability_view_audit_row("env_audit")
    assert asyncio.run(routes.application_idempotency_audit_row("forge_materialise")) == get_idempotency_audit_row(
        "forge_materialise"
    )
    assert asyncio.run(routes.application_seal_audit_row("GET", "api/v1/health/live")) == get_seal_audit_row(
        "GET /api/v1/health/live"
    )
    assert asyncio.run(routes.application_admit_write_audit_row("POST")) == get_admit_write_audit_row("POST")
    assert asyncio.run(routes.application_gate_limit_audit_row("SKELETON_GATE_MAX_BODY_BYTES")) == get_gate_limit_audit_row(
        "SKELETON_GATE_MAX_BODY_BYTES"
    )
    assert asyncio.run(routes.application_cli_shared_audit_row("config")) == get_cli_shared_audit_row("config")
    with pytest.raises(HTTPException) as missing:
        asyncio.run(routes.application_cli_shared_audit_row("missing"))
    assert missing.value.status_code == 404
