"""Regression coverage for the import-free scaffold template audit."""

from __future__ import annotations

import json

import pytest

from skeleton.__main__ import main
from skeleton.application import (
    CAPABILITY_MANIFEST_VERSION,
    TEMPLATE_AUDIT_KIND,
    capability_manifest,
    get_template_audit_row,
    template_audit_snapshot,
)


_ROW_KEYS = {
    "id",
    "in_scaffold",
    "architecture_documented",
    "scaffold_files",
    "architecture_files",
    "file_drift",
}


def test_template_audit_is_import_free(monkeypatch) -> None:
    called = False

    def should_not_import(_module_name: str):
        nonlocal called
        called = True
        raise AssertionError("template audit must not import the developer package")

    monkeypatch.setattr(
        "skeleton.application.capability_runtime.import_module",
        should_not_import,
    )
    payload = template_audit_snapshot()
    assert called is False
    assert payload["schema_version"] == CAPABILITY_MANIFEST_VERSION == 1
    assert payload["kind"] == TEMPLATE_AUDIT_KIND == "template_audit"


def test_template_audit_locks_four_scaffold_templates() -> None:
    payload = template_audit_snapshot()
    assert [row["id"] for row in payload["templates"]] == [
        "minimal-agent",
        "game-forge",
        "swarm-orchestrator",
        "api-gateway",
    ]
    assert payload["missing_from_architecture"] == []
    assert payload["missing_from_scaffold"] == []
    for row in payload["templates"]:
        assert set(row) == _ROW_KEYS
        assert row["in_scaffold"] is True
        assert row["architecture_documented"] is True
        assert row["file_drift"] == {"missing_from_architecture": [], "missing_from_public": []}
        assert row["scaffold_files"] == row["architecture_files"]


def test_capabilities_cli_template_audit_matches_python_api(capsys) -> None:
    assert main(["capabilities", "--template-audit"]) == 0
    assert json.loads(capsys.readouterr().out) == template_audit_snapshot()


def test_http_template_audit_matches_cli_payload() -> None:
    import asyncio

    from fastapi import HTTPException

    from skeleton.api import routes

    snapshot = template_audit_snapshot()
    assert asyncio.run(routes.application_template_audit()) == snapshot
    row = asyncio.run(routes.application_template_audit_row(" Game-Forge "))
    assert row == get_template_audit_row("game-forge")
    with pytest.raises(HTTPException) as missing:
        asyncio.run(routes.application_template_audit_row("missing"))
    assert missing.value.status_code == 404


def test_shared_command_template_audit_matches_snapshot_and_stays_fail_closed() -> None:
    from skeleton.application import build_runtime_command_service

    class _State:
        genesis = None

        def is_healthy(self):
            return {"overall": True}

    service = build_runtime_command_service(_State())
    identity = service.execute("capabilities")
    assert identity.ok is True
    assert identity.to_payload()["data"] == capability_manifest()

    audit = service.execute("capabilities", {"template_audit": True})
    assert audit.ok is True
    assert audit.to_payload()["data"] == template_audit_snapshot()

    invalid = service.execute("capabilities", {"template_audit": "yes"})
    assert invalid.ok is False
    both = service.execute("capabilities", {"template_audit": True, "cli_audit": True})
    assert both.ok is False
