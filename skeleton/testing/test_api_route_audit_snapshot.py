"""Regression coverage for the import-free main-router API route audit."""

from __future__ import annotations

import json

import pytest

from skeleton.__main__ import main
from skeleton.application import (
    API_ROUTE_AUDIT_KIND,
    CAPABILITY_MANIFEST_VERSION,
    api_route_audit_snapshot,
    capability_manifest,
    get_api_route_audit_row,
)


_ROW_KEYS = {
    "key",
    "method",
    "path",
    "handler",
    "architecture_documented",
    "charter_gated",
    "architecture_protected",
    "protected_drift",
}


def test_api_route_audit_is_import_free(monkeypatch) -> None:
    called = False

    def should_not_import(_module_name: str):
        nonlocal called
        called = True
        raise AssertionError("route audit must not import route modules")

    monkeypatch.setattr(
        "skeleton.application.capability_runtime.import_module",
        should_not_import,
    )
    payload = api_route_audit_snapshot()
    assert called is False
    assert payload["schema_version"] == CAPABILITY_MANIFEST_VERSION == 1
    assert payload["kind"] == API_ROUTE_AUDIT_KIND == "api_route_audit"


def test_api_route_audit_locks_main_router_parity() -> None:
    payload = api_route_audit_snapshot()
    assert payload["missing_from_architecture"] == []
    assert payload["missing_from_handlers"] == []
    assert payload["protected_mismatch"] == []
    assert payload["routes"]

    rows = {row["key"]: row for row in payload["routes"]}
    for row in payload["routes"]:
        assert set(row) == _ROW_KEYS
        assert row["architecture_documented"] is True

    submit = rows["POST /api/v1/swarm/submit"]
    assert submit["charter_gated"] is True
    assert submit["architecture_protected"] is True
    assert submit["protected_drift"] is False

    health = rows["GET /api/v1/health"]
    assert health["charter_gated"] is False
    assert health["architecture_protected"] is False


def test_capabilities_cli_route_audit_matches_python_api(capsys) -> None:
    assert main(["capabilities", "--route-audit"]) == 0
    assert json.loads(capsys.readouterr().out) == api_route_audit_snapshot()


def test_http_route_audit_matches_cli_payload() -> None:
    import asyncio

    from fastapi import HTTPException

    from skeleton.api import routes

    snapshot = api_route_audit_snapshot()
    assert asyncio.run(routes.application_api_route_audit()) == snapshot

    row = asyncio.run(routes.application_api_route_audit_row("GET", "api/v1/health"))
    assert row == get_api_route_audit_row("GET /api/v1/health")
    assert row["handler"] == "health"

    with pytest.raises(HTTPException) as missing:
        asyncio.run(routes.application_api_route_audit_row("POST", "api/v1/missing"))
    assert missing.value.status_code == 404


def test_shared_command_route_audit_matches_snapshot_and_stays_fail_closed() -> None:
    from skeleton.application import build_runtime_command_service

    class _State:
        genesis = None

        def is_healthy(self):
            return {"overall": True}

    service = build_runtime_command_service(_State())
    identity = service.execute("capabilities")
    assert identity.ok is True
    assert identity.to_payload()["data"] == capability_manifest()

    audit = service.execute("capabilities", {"route_audit": True})
    assert audit.ok is True
    assert audit.to_payload()["data"] == api_route_audit_snapshot()

    row = service.execute(
        "capabilities",
        {"route_audit": True, "route_id": "POST /api/v1/pipeline/npc"},
    )
    assert row.ok is True
    assert row.to_payload()["data"] == get_api_route_audit_row("POST /api/v1/pipeline/npc")

    invalid = service.execute("capabilities", {"route_audit": 1})
    assert invalid.ok is False
    assert invalid.to_payload()["error"]["code"] == "invalid_argument"

    both = service.execute("capabilities", {"route_audit": True, "export_audit": True})
    assert both.ok is False
    assert both.to_payload()["error"]["code"] == "invalid_argument"
