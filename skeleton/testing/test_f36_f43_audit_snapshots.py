"""Regression coverage for F-36..F-43 import-free audits."""

from __future__ import annotations

import json

import pytest

from skeleton.__main__ import main
from skeleton.application import (
    APP_ROUTE_AUDIT_KIND,
    CAPABILITY_MANIFEST_VERSION,
    CHARTER_AUDIT_KIND,
    CONTRACT_AUDIT_KIND,
    ENV_FLAG_AUDIT_KIND,
    LIVE_HMAC_AUDIT_KIND,
    NESTED_ROUTER_AUDIT_KIND,
    app_route_audit_snapshot,
    capability_manifest,
    charter_audit_snapshot,
    contract_audit_snapshot,
    env_flag_audit_snapshot,
    get_app_route_audit_row,
    get_charter_audit_row,
    get_contract_audit_row,
    get_env_flag_audit_row,
    get_live_hmac_audit_row,
    get_nested_router_audit_row,
    live_hmac_audit_snapshot,
    nested_router_audit_snapshot,
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


def test_app_route_audit_locks_inline_undocumented_handlers(monkeypatch) -> None:
    _assert_import_free(monkeypatch, app_route_audit_snapshot, APP_ROUTE_AUDIT_KIND)
    payload = app_route_audit_snapshot()
    assert payload["missing_from_architecture"] == ["GET /", "GET /cortex/status"]
    rows = {row["key"]: row for row in payload["routes"]}
    assert rows["GET /"]["handler"] == "root"
    assert rows["GET /cortex/status"]["handler"] == "cortex_status"
    assert rows["GET /"]["architecture_documented"] is False
    assert rows["GET /"]["charter_gated"] is False


def test_charter_audit_locks_six_main_router_pairs(monkeypatch) -> None:
    _assert_import_free(monkeypatch, charter_audit_snapshot, CHARTER_AUDIT_KIND)
    payload = charter_audit_snapshot()
    assert payload["pairs"] == [
        "forge.archetype",
        "forge.blueprint",
        "forge.intake",
        "forge.materialise",
        "forge.run",
        "swarm.submit",
    ]
    assert payload["undocumented"] == []
    rows = {row["key"]: row for row in payload["routes"]}
    submit = rows["POST /api/v1/swarm/submit"]
    assert submit["pair"] == "swarm.submit"
    assert submit["architecture_protected"] is True
    assert rows["POST /api/v1/gameforge/intake"]["source"] == "main"


def test_contract_audit_locks_runtime_handler_parity(monkeypatch) -> None:
    _assert_import_free(monkeypatch, contract_audit_snapshot, CONTRACT_AUDIT_KIND)
    payload = contract_audit_snapshot()
    assert payload["missing_from_runtime"] == []
    assert payload["missing_from_contract"] == []
    rows = {row["command"]: row for row in payload["commands"]}
    assert set(rows) == {"run", "tool", "memory", "status", "configuration", "capabilities", "admin"}
    assert rows["run"]["auth_required"] is True
    assert rows["status"]["auth_required"] is False
    assert rows["admin"]["mutating"] is True


def test_live_hmac_audit_locks_probe_only_open_live_handlers(monkeypatch) -> None:
    _assert_import_free(monkeypatch, live_hmac_audit_snapshot, LIVE_HMAC_AUDIT_KIND)
    payload = live_hmac_audit_snapshot()
    assert payload["hmac_open_live"] == ["GET /api/v1/health/live", "GET /api/v1/health/ready"]
    assert payload["undocumented_open_prefixes"] == ["/health", "/ready"]
    rows = {row["key"]: row for row in payload["routes"]}
    assert rows["GET /api/v1/health"]["hmac_open"] is False
    assert rows["GET /"]["surface"] == "create_app"
    assert rows["GET /"]["hmac_open"] is False
    assert rows["GET /cortex/status"]["hmac_open"] is False


def test_nested_router_audit_locks_gameforge_command_include(monkeypatch) -> None:
    _assert_import_free(monkeypatch, nested_router_audit_snapshot, NESTED_ROUTER_AUDIT_KIND)
    payload = nested_router_audit_snapshot()
    assert len(payload["includes"]) == 1
    row = payload["includes"][0]
    assert row["host_module"] == "skeleton.api.gameforge_routes"
    assert row["included_module"] == "skeleton.api.command_routes"
    assert row["prefix"] == ""


def test_env_flag_audit_locks_own_and_seal_names(monkeypatch) -> None:
    _assert_import_free(monkeypatch, env_flag_audit_snapshot, ENV_FLAG_AUDIT_KIND)
    payload = env_flag_audit_snapshot()
    assert payload["names"] == [
        "SKELETON_PUBLIC_DEV_SURFACES",
        "GF_SEAL_SECRET",
        "GF_SEAL_KEYRING",
        "SKELETON_OWN",
    ]
    rows = {row["name"]: row for row in payload["flags"]}
    assert rows["SKELETON_OWN"]["module"] == "skeleton.cortex.live"


def test_cli_http_and_command_parity_for_new_audits(capsys) -> None:
    import asyncio

    from fastapi import HTTPException

    from skeleton.api import routes

    pairs = [
        (["capabilities", "--app-audit"], app_route_audit_snapshot, routes.application_app_route_audit, "app_audit"),
        (["capabilities", "--charter-audit"], charter_audit_snapshot, routes.application_charter_audit, "charter_audit"),
        (["capabilities", "--contract-audit"], contract_audit_snapshot, routes.application_contract_audit, "contract_audit"),
        (["capabilities", "--live-hmac-audit"], live_hmac_audit_snapshot, routes.application_live_hmac_audit, "live_hmac_audit"),
        (["capabilities", "--nested-audit"], nested_router_audit_snapshot, routes.application_nested_router_audit, "nested_audit"),
        (["capabilities", "--env-audit"], env_flag_audit_snapshot, routes.application_env_flag_audit, "env_audit"),
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

    row = asyncio.run(routes.application_app_route_audit_row("GET", "cortex/status"))
    assert row == get_app_route_audit_row("GET /cortex/status")
    assert asyncio.run(routes.application_charter_audit_row("POST", "api/v1/swarm/submit")) == get_charter_audit_row(
        "POST /api/v1/swarm/submit"
    )
    assert asyncio.run(routes.application_contract_audit_row(" Run ")) == get_contract_audit_row("run")
    assert asyncio.run(routes.application_live_hmac_audit_row("GET", "api/v1/health/live")) == get_live_hmac_audit_row(
        "GET /api/v1/health/live"
    )
    assert asyncio.run(routes.application_nested_router_audit_row("skeleton.api.gameforge_routes")) == get_nested_router_audit_row(
        "skeleton.api.gameforge_routes"
    )
    assert asyncio.run(routes.application_env_flag_audit_row("SKELETON_OWN")) == get_env_flag_audit_row("SKELETON_OWN")
    with pytest.raises(HTTPException) as missing:
        asyncio.run(routes.application_env_flag_audit_row("MISSING"))
    assert missing.value.status_code == 404
