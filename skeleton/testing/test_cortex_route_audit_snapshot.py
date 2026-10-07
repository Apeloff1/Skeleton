"""Regression coverage for the import-free unmounted cortex-route audit."""

from __future__ import annotations

import json

import pytest

from skeleton.__main__ import main
from skeleton.application import (
    CAPABILITY_MANIFEST_VERSION,
    CORTEX_ROUTE_AUDIT_KIND,
    capability_manifest,
    cortex_route_audit_snapshot,
    get_cortex_route_audit_row,
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


def test_cortex_route_audit_is_import_free(monkeypatch) -> None:
    called = False

    def should_not_import(_module_name: str):
        nonlocal called
        called = True
        raise AssertionError("cortex audit must not import cortex route modules")

    monkeypatch.setattr(
        "skeleton.application.capability_runtime.import_module",
        should_not_import,
    )
    payload = cortex_route_audit_snapshot()
    assert called is False
    assert payload["schema_version"] == CAPABILITY_MANIFEST_VERSION == 1
    assert payload["kind"] == CORTEX_ROUTE_AUDIT_KIND == "cortex_route_audit"


def test_cortex_route_audit_locks_unmounted_undocumented_handlers() -> None:
    payload = cortex_route_audit_snapshot()
    assert len(payload["routes"]) == 52
    assert len(payload["missing_from_architecture"]) == 52
    assert payload["protected_mismatch"] == []
    rows = {row["key"]: row for row in payload["routes"]}
    for row in payload["routes"]:
        assert set(row) == _ROW_KEYS
        assert row["source"] == "cortex"
        assert row["architecture_documented"] is False
        assert row["charter_gated"] is False
        assert row["seal_gated"] is False

    policy = rows["GET /api/v1/policy/state"]
    assert policy["handler"] == "get_policy_state"
    meta = rows["GET /api/v1/meta"]
    assert meta["handler"] == "get_meta"
    assert "GET /api/v1/health" not in rows
    assert "POST /api/v1/gameforge/run" not in rows


def test_capabilities_cli_cortex_audit_matches_python_api(capsys) -> None:
    assert main(["capabilities", "--cortex-audit"]) == 0
    assert json.loads(capsys.readouterr().out) == cortex_route_audit_snapshot()


def test_http_cortex_audit_matches_cli_payload() -> None:
    import asyncio

    from fastapi import HTTPException

    from skeleton.api import routes

    snapshot = cortex_route_audit_snapshot()
    assert asyncio.run(routes.application_cortex_route_audit()) == snapshot
    row = asyncio.run(routes.application_cortex_route_audit_row("GET", "api/v1/policy/state"))
    assert row == get_cortex_route_audit_row("GET /api/v1/policy/state")
    with pytest.raises(HTTPException) as missing:
        asyncio.run(routes.application_cortex_route_audit_row("GET", "api/v1/missing"))
    assert missing.value.status_code == 404


def test_shared_command_cortex_audit_matches_snapshot_and_stays_fail_closed() -> None:
    from skeleton.application import build_runtime_command_service

    class _State:
        genesis = None

        def is_healthy(self):
            return {"overall": True}

    service = build_runtime_command_service(_State())
    identity = service.execute("capabilities")
    assert identity.ok is True
    assert identity.to_payload()["data"] == capability_manifest()

    audit = service.execute("capabilities", {"cortex_audit": True})
    assert audit.ok is True
    assert audit.to_payload()["data"] == cortex_route_audit_snapshot()

    invalid = service.execute("capabilities", {"cortex_audit": 1})
    assert invalid.ok is False
    both = service.execute("capabilities", {"cortex_audit": True, "domain_audit": True})
    assert both.ok is False
