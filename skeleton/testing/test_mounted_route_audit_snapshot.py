"""Regression coverage for the import-free create_app-mounted sidecar audit."""

from __future__ import annotations

import json

import pytest

from skeleton.__main__ import main
from skeleton.application import (
    CAPABILITY_MANIFEST_VERSION,
    MOUNTED_ROUTE_AUDIT_KIND,
    capability_manifest,
    get_mounted_route_audit_row,
    mounted_route_audit_snapshot,
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


def test_mounted_route_audit_is_import_free(monkeypatch) -> None:
    called = False

    def should_not_import(_module_name: str):
        nonlocal called
        called = True
        raise AssertionError("mounted audit must not import API route modules")

    monkeypatch.setattr(
        "skeleton.application.capability_runtime.import_module",
        should_not_import,
    )
    payload = mounted_route_audit_snapshot()
    assert called is False
    assert payload["schema_version"] == CAPABILITY_MANIFEST_VERSION == 1
    assert payload["kind"] == MOUNTED_ROUTE_AUDIT_KIND == "mounted_route_audit"


def test_mounted_route_audit_locks_swarm_family_and_cockpit() -> None:
    payload = mounted_route_audit_snapshot()
    assert len(payload["routes"]) == 71
    assert len(payload["missing_from_architecture"]) == 71
    assert payload["protected_mismatch"] == []
    sources = {row["source"] for row in payload["routes"]}
    assert "cockpit" in sources
    assert "swarm_routes" in sources
    assert "gameforge" not in sources
    assert "command" not in sources
    rows = {row["key"]: row for row in payload["routes"]}
    for row in payload["routes"]:
        assert set(row) == _ROW_KEYS
        assert row["architecture_documented"] is False

    cockpit = rows["GET /cockpit"]
    assert cockpit["source"] == "cockpit"
    assert cockpit["handler"] == "cockpit"

    status = rows["GET /api/v1/swarm/status"]
    assert status["source"] == "swarm_routes"
    assert "GET /api/v1/health" not in rows
    assert "POST /api/v1/gameforge/run" not in rows
    assert "GET /api/v1/commands/contracts" not in rows


def test_capabilities_cli_mounted_audit_matches_python_api(capsys) -> None:
    assert main(["capabilities", "--mounted-audit"]) == 0
    assert json.loads(capsys.readouterr().out) == mounted_route_audit_snapshot()


def test_http_mounted_audit_matches_cli_payload() -> None:
    import asyncio

    from fastapi import HTTPException

    from skeleton.api import routes

    snapshot = mounted_route_audit_snapshot()
    assert asyncio.run(routes.application_mounted_route_audit()) == snapshot
    row = asyncio.run(routes.application_mounted_route_audit_row("GET", "cockpit"))
    assert row == get_mounted_route_audit_row("GET /cockpit")
    with pytest.raises(HTTPException) as missing:
        asyncio.run(routes.application_mounted_route_audit_row("GET", "api/v1/missing"))
    assert missing.value.status_code == 404


def test_shared_command_mounted_audit_matches_snapshot_and_stays_fail_closed() -> None:
    from skeleton.application import build_runtime_command_service

    class _State:
        genesis = None

        def is_healthy(self):
            return {"overall": True}

    service = build_runtime_command_service(_State())
    identity = service.execute("capabilities")
    assert identity.ok is True
    assert identity.to_payload()["data"] == capability_manifest()

    audit = service.execute("capabilities", {"mounted_audit": True})
    assert audit.ok is True
    assert audit.to_payload()["data"] == mounted_route_audit_snapshot()

    invalid = service.execute("capabilities", {"mounted_audit": 1})
    assert invalid.ok is False
    both = service.execute("capabilities", {"mounted_audit": True, "route_audit": True})
    assert both.ok is False
