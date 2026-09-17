"""Regression coverage for the import-free GameForge/command sidecar audit."""

from __future__ import annotations

import json

import pytest

from skeleton.__main__ import main
from skeleton.application import (
    CAPABILITY_MANIFEST_VERSION,
    SIDECAR_ROUTE_AUDIT_KIND,
    capability_manifest,
    get_sidecar_route_audit_row,
    sidecar_route_audit_snapshot,
)


_ROW_KEYS = {
    "key",
    "method",
    "path",
    "handler",
    "source",
    "architecture_documented",
    "charter_gated",
    "seal_gated",
    "architecture_protected",
    "protected_drift",
}


def test_sidecar_route_audit_is_import_free(monkeypatch) -> None:
    called = False

    def should_not_import(_module_name: str):
        nonlocal called
        called = True
        raise AssertionError("sidecar audit must not import API route modules")

    monkeypatch.setattr(
        "skeleton.application.capability_runtime.import_module",
        should_not_import,
    )
    payload = sidecar_route_audit_snapshot()
    assert called is False
    assert payload["schema_version"] == CAPABILITY_MANIFEST_VERSION == 1
    assert payload["kind"] == SIDECAR_ROUTE_AUDIT_KIND == "sidecar_route_audit"


def test_sidecar_route_audit_locks_duplicate_gameforge_and_undocumented_commands() -> None:
    payload = sidecar_route_audit_snapshot()
    assert payload["missing_from_architecture"] == [
        "GET /api/v1/commands/contracts",
        "POST /api/v1/commands/execute/{command}",
    ]
    assert "POST /api/v1/gameforge/intake" in payload["protected_mismatch"]
    assert "POST /api/v1/gameforge/run" in payload["protected_mismatch"]
    rows = {row["key"]: row for row in payload["routes"]}
    for row in payload["routes"]:
        assert set(row) == _ROW_KEYS

    intake = rows["POST /api/v1/gameforge/intake"]
    assert intake["source"] == "gameforge"
    assert intake["architecture_documented"] is True
    assert intake["architecture_protected"] is True
    assert intake["charter_gated"] is False
    assert intake["seal_gated"] is False
    assert intake["protected_drift"] is True

    run = rows["POST /api/v1/gameforge/run"]
    assert run["seal_gated"] is True
    assert run["charter_gated"] is False
    assert run["protected_drift"] is True

    contracts = rows["GET /api/v1/commands/contracts"]
    assert contracts["source"] == "command"
    assert contracts["architecture_documented"] is False
    assert contracts["charter_gated"] is False
    assert contracts["seal_gated"] is False


def test_capabilities_cli_sidecar_audit_matches_python_api(capsys) -> None:
    assert main(["capabilities", "--sidecar-audit"]) == 0
    assert json.loads(capsys.readouterr().out) == sidecar_route_audit_snapshot()


def test_http_sidecar_audit_matches_cli_payload() -> None:
    import asyncio

    from fastapi import HTTPException

    from skeleton.api import routes

    snapshot = sidecar_route_audit_snapshot()
    assert asyncio.run(routes.application_sidecar_route_audit()) == snapshot
    row = asyncio.run(routes.application_sidecar_route_audit_row("POST", "api/v1/gameforge/run"))
    assert row == get_sidecar_route_audit_row("POST /api/v1/gameforge/run")
    with pytest.raises(HTTPException) as missing:
        asyncio.run(routes.application_sidecar_route_audit_row("POST", "api/v1/missing"))
    assert missing.value.status_code == 404


def test_shared_command_sidecar_audit_matches_snapshot_and_stays_fail_closed() -> None:
    from skeleton.application import build_runtime_command_service

    class _State:
        genesis = None

        def is_healthy(self):
            return {"overall": True}

    service = build_runtime_command_service(_State())
    identity = service.execute("capabilities")
    assert identity.ok is True
    assert identity.to_payload()["data"] == capability_manifest()

    audit = service.execute("capabilities", {"sidecar_audit": True})
    assert audit.ok is True
    assert audit.to_payload()["data"] == sidecar_route_audit_snapshot()

    invalid = service.execute("capabilities", {"sidecar_audit": 1})
    assert invalid.ok is False
    both = service.execute("capabilities", {"sidecar_audit": True, "route_audit": True})
    assert both.ok is False
