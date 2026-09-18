"""Regression coverage for the import-free HMAC open-prefix audit."""

from __future__ import annotations

import json

import pytest

from skeleton.__main__ import main
from skeleton.application import (
    CAPABILITY_MANIFEST_VERSION,
    HMAC_OPEN_AUDIT_KIND,
    capability_manifest,
    get_hmac_open_audit_row,
    hmac_open_audit_snapshot,
)


_ROW_KEYS = {
    "key",
    "method",
    "path",
    "architecture_protected",
    "hmac_open",
    "hmac_sealed_but_documented_unprotected",
    "hmac_open_but_documented_protected",
}


def test_hmac_open_audit_is_import_free(monkeypatch) -> None:
    called = False

    def should_not_import(_module_name: str):
        nonlocal called
        called = True
        raise AssertionError("hmac audit must not import API route modules")

    monkeypatch.setattr(
        "skeleton.application.capability_runtime.import_module",
        should_not_import,
    )
    payload = hmac_open_audit_snapshot()
    assert called is False
    assert payload["schema_version"] == CAPABILITY_MANIFEST_VERSION == 1
    assert payload["kind"] == HMAC_OPEN_AUDIT_KIND == "hmac_open_audit"


def test_hmac_open_audit_locks_probe_only_open_surface() -> None:
    payload = hmac_open_audit_snapshot()
    assert payload["open_prefixes"] == [
        "/health",
        "/ready",
        "/api/v1/health/live",
        "/api/v1/health/ready",
    ]
    assert payload["runtime_root_open"] is True
    assert "/api/v1/health" in payload["dev_open_prefixes"]
    assert payload["hmac_open_protected"] == []
    assert payload["undocumented_open_prefixes"] == ["/health", "/ready"]
    assert payload["hmac_sealed_unprotected"]
    assert payload["routes"]

    rows = {row["key"]: row for row in payload["routes"]}
    for row in payload["routes"]:
        assert set(row) == _ROW_KEYS

    health = rows["GET /api/v1/health"]
    assert health["architecture_protected"] is False
    assert health["hmac_open"] is False
    assert health["hmac_sealed_but_documented_unprotected"] is True
    assert "GET /api/v1/health" in payload["hmac_sealed_unprotected"]

    live = rows["GET /api/v1/health/live"]
    assert live["architecture_protected"] is False
    assert live["hmac_open"] is True
    assert live["hmac_sealed_but_documented_unprotected"] is False
    assert "GET /api/v1/health/live" not in payload["hmac_sealed_unprotected"]

    forge = rows["POST /api/v1/forge/blueprint"]
    assert forge["architecture_protected"] is True
    assert forge["hmac_open"] is False
    assert forge["hmac_open_but_documented_protected"] is False


def test_capabilities_cli_hmac_audit_matches_python_api(capsys) -> None:
    assert main(["capabilities", "--hmac-audit"]) == 0
    assert json.loads(capsys.readouterr().out) == hmac_open_audit_snapshot()


def test_http_hmac_audit_matches_cli_payload() -> None:
    import asyncio

    from fastapi import HTTPException

    from skeleton.api import routes

    snapshot = hmac_open_audit_snapshot()
    assert asyncio.run(routes.application_hmac_open_audit()) == snapshot

    row = asyncio.run(routes.application_hmac_open_audit_row("GET", "api/v1/health/live"))
    assert row == get_hmac_open_audit_row("GET /api/v1/health/live")
    assert row["hmac_open"] is True

    with pytest.raises(HTTPException) as missing:
        asyncio.run(routes.application_hmac_open_audit_row("POST", "api/v1/missing"))
    assert missing.value.status_code == 404


def test_shared_command_hmac_audit_matches_snapshot_and_stays_fail_closed() -> None:
    from skeleton.application import build_runtime_command_service

    class _State:
        genesis = None

        def is_healthy(self):
            return {"overall": True}

    service = build_runtime_command_service(_State())
    identity = service.execute("capabilities")
    assert identity.ok is True
    assert identity.to_payload()["data"] == capability_manifest()

    audit = service.execute("capabilities", {"hmac_audit": True})
    assert audit.ok is True
    assert audit.to_payload()["data"] == hmac_open_audit_snapshot()

    row = service.execute(
        "capabilities",
        {"hmac_audit": True, "route_id": "GET /api/v1/health"},
    )
    assert row.ok is True
    assert row.to_payload()["data"] == get_hmac_open_audit_row("GET /api/v1/health")

    invalid = service.execute("capabilities", {"hmac_audit": 1})
    assert invalid.ok is False
    assert invalid.to_payload()["error"]["code"] == "invalid_argument"

    both = service.execute("capabilities", {"hmac_audit": True, "route_audit": True})
    assert both.ok is False
    assert both.to_payload()["error"]["code"] == "invalid_argument"
