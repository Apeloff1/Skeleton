"""Regression coverage for the import-free developer CLI audit."""

from __future__ import annotations

import json

import pytest

from skeleton.__main__ import main
from skeleton.application import (
    CAPABILITY_MANIFEST_VERSION,
    DEVELOPER_CLI_AUDIT_KIND,
    capability_manifest,
    developer_cli_audit_snapshot,
    get_developer_cli_audit_row,
)


_ROW_KEYS = {
    "command",
    "architecture_documented",
    "in_registry",
    "in_cli_dispatch",
    "runtime_present",
    "args",
    "description",
}


def test_developer_cli_audit_is_import_free(monkeypatch) -> None:
    called = False

    def should_not_import(_module_name: str):
        nonlocal called
        called = True
        raise AssertionError("cli audit must not import the developer package")

    monkeypatch.setattr(
        "skeleton.application.capability_runtime.import_module",
        should_not_import,
    )
    payload = developer_cli_audit_snapshot()
    assert called is False
    assert payload["schema_version"] == CAPABILITY_MANIFEST_VERSION == 1
    assert payload["kind"] == DEVELOPER_CLI_AUDIT_KIND == "developer_cli_audit"


def test_developer_cli_audit_locks_registry_and_help_split() -> None:
    payload = developer_cli_audit_snapshot()
    assert payload["missing_from_architecture"] == ["snapshot", "restore", "snapshots"]
    assert payload["missing_from_runtime"] == []
    rows = {row["command"]: row for row in payload["commands"]}
    for row in payload["commands"]:
        assert set(row) == _ROW_KEYS
        assert row["runtime_present"] is True

    scaffold = rows["scaffold"]
    assert scaffold["architecture_documented"] is True
    assert scaffold["in_registry"] is True
    assert scaffold["in_cli_dispatch"] is False

    listed = rows["list-templates"]
    assert listed["architecture_documented"] is True
    assert listed["in_registry"] is False
    assert listed["in_cli_dispatch"] is True

    snapshot = rows["snapshot"]
    assert snapshot["architecture_documented"] is False
    assert snapshot["in_registry"] is True


def test_capabilities_cli_developer_audit_matches_python_api(capsys) -> None:
    assert main(["capabilities", "--cli-audit"]) == 0
    assert json.loads(capsys.readouterr().out) == developer_cli_audit_snapshot()


def test_http_developer_cli_audit_matches_cli_payload() -> None:
    import asyncio

    from fastapi import HTTPException

    from skeleton.api import routes

    snapshot = developer_cli_audit_snapshot()
    assert asyncio.run(routes.application_developer_cli_audit()) == snapshot
    row = asyncio.run(routes.application_developer_cli_audit_row(" Scaffold "))
    assert row == get_developer_cli_audit_row("scaffold")
    with pytest.raises(HTTPException) as missing:
        asyncio.run(routes.application_developer_cli_audit_row("missing"))
    assert missing.value.status_code == 404


def test_shared_command_cli_audit_matches_snapshot_and_stays_fail_closed() -> None:
    from skeleton.application import build_runtime_command_service

    class _State:
        genesis = None

        def is_healthy(self):
            return {"overall": True}

    service = build_runtime_command_service(_State())
    identity = service.execute("capabilities")
    assert identity.ok is True
    assert identity.to_payload()["data"] == capability_manifest()

    audit = service.execute("capabilities", {"cli_audit": True})
    assert audit.ok is True
    assert audit.to_payload()["data"] == developer_cli_audit_snapshot()

    row = service.execute("capabilities", {"cli_audit": True, "command_id": "docs"})
    assert row.ok is True
    assert row.to_payload()["data"] == get_developer_cli_audit_row("docs")

    invalid = service.execute("capabilities", {"cli_audit": 1})
    assert invalid.ok is False
    both = service.execute("capabilities", {"cli_audit": True, "hmac_audit": True})
    assert both.ok is False
