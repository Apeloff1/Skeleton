"""Regression coverage for the import-free main CLI help/dispatch audit."""

from __future__ import annotations

import json

import pytest

from skeleton.__main__ import main
from skeleton.application import (
    CAPABILITY_MANIFEST_VERSION,
    MAIN_CLI_AUDIT_KIND,
    capability_manifest,
    get_main_cli_audit_row,
    main_cli_audit_snapshot,
)


_ROW_KEYS = {"command", "in_help", "in_dispatch", "runtime_present"}
_COMMANDS = [
    "run",
    "forge",
    "test",
    "dev",
    "eras",
    "generations",
    "plan",
    "cockpit",
    "walk",
    "contracts",
    "capabilities",
    "command",
    "status",
    "config",
    "help",
]


def test_main_cli_audit_is_import_free(monkeypatch) -> None:
    called = False

    def should_not_import(_module_name: str):
        nonlocal called
        called = True
        raise AssertionError("main CLI audit must not import genesis")

    monkeypatch.setattr(
        "skeleton.application.capability_runtime.import_module",
        should_not_import,
    )
    payload = main_cli_audit_snapshot()
    assert called is False
    assert payload["schema_version"] == CAPABILITY_MANIFEST_VERSION == 1
    assert payload["kind"] == MAIN_CLI_AUDIT_KIND == "main_cli_audit"


def test_main_cli_audit_locks_help_dispatch_parity_and_help_aliases() -> None:
    payload = main_cli_audit_snapshot()
    assert [row["command"] for row in payload["commands"]] == _COMMANDS
    assert payload["aliases"] == ["-h", "--help"]
    assert payload["missing_from_help"] == []
    assert payload["missing_from_dispatch"] == []
    for row in payload["commands"]:
        assert set(row) == _ROW_KEYS
        assert row["in_help"] is True
        assert row["in_dispatch"] is True
        assert row["runtime_present"] is True


def test_capabilities_cli_main_cli_audit_matches_python_api(capsys) -> None:
    assert main(["capabilities", "--main-cli-audit"]) == 0
    assert json.loads(capsys.readouterr().out) == main_cli_audit_snapshot()


def test_http_main_cli_audit_matches_cli_payload() -> None:
    import asyncio

    from fastapi import HTTPException

    from skeleton.api import routes

    snapshot = main_cli_audit_snapshot()
    assert asyncio.run(routes.application_main_cli_audit()) == snapshot
    row = asyncio.run(routes.application_main_cli_audit_row(" Capabilities "))
    assert row == get_main_cli_audit_row("capabilities")
    with pytest.raises(HTTPException) as missing:
        asyncio.run(routes.application_main_cli_audit_row("missing"))
    assert missing.value.status_code == 404


def test_shared_command_main_cli_audit_matches_snapshot_and_stays_fail_closed() -> None:
    from skeleton.application import build_runtime_command_service

    class _State:
        genesis = None

        def is_healthy(self):
            return {"overall": True}

    service = build_runtime_command_service(_State())
    identity = service.execute("capabilities")
    assert identity.ok is True
    assert identity.to_payload()["data"] == capability_manifest()

    audit = service.execute("capabilities", {"main_cli_audit": True})
    assert audit.ok is True
    assert audit.to_payload()["data"] == main_cli_audit_snapshot()

    invalid = service.execute("capabilities", {"main_cli_audit": 1})
    assert invalid.ok is False
    both = service.execute("capabilities", {"main_cli_audit": True, "cli_audit": True})
    assert both.ok is False
