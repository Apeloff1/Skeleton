"""Regression coverage for the import-free gate-domain audit."""

from __future__ import annotations

import json

import pytest

from skeleton.__main__ import main
from skeleton.application import (
    CAPABILITY_MANIFEST_VERSION,
    GATE_DOMAIN_AUDIT_KIND,
    capability_manifest,
    gate_domain_audit_snapshot,
    get_gate_domain_audit_row,
)


_ROW_KEYS = {"path", "domain", "mapped", "architecture_documented"}
_UNUSED = [
    ("/api/v1/cortex", "cognition"),
    ("/api/fabric", "fabric"),
    ("/api/legions", "legions"),
    ("/api/swarm", "swarm"),
    ("/api/governance", "governance"),
    ("/api/cognition", "cognition"),
    ("/api/lafs", "lafs"),
    ("/api/studio", "studio"),
    ("/api/sagas", "fabric"),
    ("/api/court", "court"),
    ("/cortex", "cognition"),
    ("/cockpit", "interface"),
    ("/docs", "interface"),
    ("/openapi.json", "interface"),
    ("/redoc", "interface"),
]


def test_gate_domain_audit_is_import_free(monkeypatch) -> None:
    called = False

    def should_not_import(_module_name: str):
        nonlocal called
        called = True
        raise AssertionError("domain audit must not import API route modules")

    monkeypatch.setattr(
        "skeleton.application.capability_runtime.import_module",
        should_not_import,
    )
    payload = gate_domain_audit_snapshot()
    assert called is False
    assert payload["schema_version"] == CAPABILITY_MANIFEST_VERSION == 1
    assert payload["kind"] == GATE_DOMAIN_AUDIT_KIND == "gate_domain_audit"


def test_gate_domain_audit_locks_documented_paths_and_unused_prefixes() -> None:
    payload = gate_domain_audit_snapshot()
    assert payload["unmapped_documented"] == []
    assert [(row["prefix"], row["domain"]) for row in payload["unused_prefixes"]] == _UNUSED
    rows = {row["path"]: row for row in payload["routes"]}
    for row in payload["routes"]:
        assert set(row) == _ROW_KEYS
        assert row["mapped"] is True
        assert row["architecture_documented"] is True

    health = rows["/api/v1/health"]
    assert health["domain"] == "observability"
    forge = rows["/api/v1/forge/blueprint"]
    assert forge["domain"] == "forge"
    submit = rows["/api/v1/swarm/submit"]
    assert submit["domain"] == "swarm"


def test_capabilities_cli_domain_audit_matches_python_api(capsys) -> None:
    assert main(["capabilities", "--domain-audit"]) == 0
    assert json.loads(capsys.readouterr().out) == gate_domain_audit_snapshot()


def test_http_domain_audit_matches_cli_payload() -> None:
    import asyncio

    from fastapi import HTTPException

    from skeleton.api import routes

    snapshot = gate_domain_audit_snapshot()
    assert asyncio.run(routes.application_gate_domain_audit()) == snapshot
    row = asyncio.run(routes.application_gate_domain_audit_row("api/v1/health"))
    assert row == get_gate_domain_audit_row("/api/v1/health")
    with pytest.raises(HTTPException) as missing:
        asyncio.run(routes.application_gate_domain_audit_row("api/v1/missing"))
    assert missing.value.status_code == 404


def test_shared_command_domain_audit_matches_snapshot_and_stays_fail_closed() -> None:
    from skeleton.application import build_runtime_command_service

    class _State:
        genesis = None

        def is_healthy(self):
            return {"overall": True}

    service = build_runtime_command_service(_State())
    identity = service.execute("capabilities")
    assert identity.ok is True
    assert identity.to_payload()["data"] == capability_manifest()

    audit = service.execute("capabilities", {"domain_audit": True})
    assert audit.ok is True
    assert audit.to_payload()["data"] == gate_domain_audit_snapshot()

    invalid = service.execute("capabilities", {"domain_audit": 1})
    assert invalid.ok is False
    both = service.execute("capabilities", {"domain_audit": True, "sidecar_audit": True})
    assert both.ok is False
