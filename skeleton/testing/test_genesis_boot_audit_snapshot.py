"""Regression coverage for the import-free genesis boot audit."""

from __future__ import annotations

import json

import pytest

from skeleton.__main__ import main
from skeleton.application import (
    CAPABILITY_MANIFEST_VERSION,
    GENESIS_BOOT_AUDIT_KIND,
    capability_manifest,
    genesis_boot_audit_snapshot,
    get_genesis_boot_audit_row,
)


_EXPECTED_PHASES = (
    "foundation",
    "kernel",
    "memory",
    "intelligence",
    "swarm",
    "resilience",
    "interface",
    "forge",
    "galaxy",
    "contexts",
    "support",
    "cortex",
)
_ROW_KEYS = {
    "phase",
    "listed_in_boot_phases",
    "appended_to_report",
    "genesis_handles",
    "documented_subsystems",
}


def test_genesis_boot_audit_is_import_free(monkeypatch) -> None:
    called = False

    def should_not_import(_module_name: str):
        nonlocal called
        called = True
        raise AssertionError("boot audit must not import genesis")

    monkeypatch.setattr(
        "skeleton.application.capability_runtime.import_module",
        should_not_import,
    )
    payload = genesis_boot_audit_snapshot()
    assert called is False
    assert payload["schema_version"] == CAPABILITY_MANIFEST_VERSION == 1
    assert payload["kind"] == GENESIS_BOOT_AUDIT_KIND == "genesis_boot_audit"


def test_genesis_boot_audit_locks_phase_documentation_drift() -> None:
    payload = genesis_boot_audit_snapshot()
    assert [row["phase"] for row in payload["phases"]] == list(_EXPECTED_PHASES)
    assert payload["missing_from_boot_phases"] == [
        "foundation",
        "forge",
        "galaxy",
        "contexts",
        "support",
    ]
    assert payload["missing_from_genesis"] == []

    rows = {row["phase"]: row for row in payload["phases"]}
    for row in payload["phases"]:
        assert set(row) == _ROW_KEYS
        assert row["appended_to_report"] is True

    assert rows["kernel"]["listed_in_boot_phases"] is True
    assert rows["cortex"]["listed_in_boot_phases"] is True
    assert rows["foundation"]["listed_in_boot_phases"] is False
    assert rows["galaxy"]["listed_in_boot_phases"] is False
    assert rows["foundation"]["genesis_handles"] == [
        "dag",
        "journal",
        "replay",
        "ocap",
        "membrane",
        "temporal",
    ]
    assert rows["galaxy"]["genesis_handles"] == [
        "kag_sync",
        "galaxy_bridge",
        "galaxy",
        "galaxy_transport",
        "consensus",
        "election",
        "fleet",
        "byzantine",
    ]
    assert "EventBus" in rows["kernel"]["documented_subsystems"]
    assert "JeevesCortex" in rows["cortex"]["documented_subsystems"]


def test_capabilities_cli_boot_audit_matches_python_api(capsys) -> None:
    assert main(["capabilities", "--boot-audit"]) == 0
    assert json.loads(capsys.readouterr().out) == genesis_boot_audit_snapshot()


def test_capabilities_cli_rejects_combined_boot_and_plane_audit(capsys) -> None:
    assert main(["capabilities", "--boot-audit", "--plane-audit"]) == 2
    assert "mutually exclusive" in capsys.readouterr().out


def test_http_genesis_boot_audit_matches_cli_payload() -> None:
    import asyncio

    from fastapi import HTTPException

    from skeleton.api import routes

    snapshot = genesis_boot_audit_snapshot()
    assert asyncio.run(routes.application_genesis_boot_audit()) == snapshot

    galaxy = asyncio.run(routes.application_genesis_boot_audit_row(" Galaxy "))
    assert galaxy == get_genesis_boot_audit_row("galaxy")
    assert galaxy["phase"] == "galaxy"
    assert galaxy["listed_in_boot_phases"] is False

    with pytest.raises(HTTPException) as missing:
        asyncio.run(routes.application_genesis_boot_audit_row("organism"))
    assert missing.value.status_code == 404

    with pytest.raises(HTTPException) as empty:
        asyncio.run(routes.application_genesis_boot_audit_row("   "))
    assert empty.value.status_code == 422


def test_shared_command_boot_audit_matches_snapshot_and_stays_fail_closed() -> None:
    from skeleton.application import build_runtime_command_service

    class _State:
        genesis = None

        def is_healthy(self):
            return {"overall": True}

    service = build_runtime_command_service(_State())
    identity = service.execute("capabilities")
    assert identity.ok is True
    assert identity.to_payload()["data"] == capability_manifest()

    audit = service.execute("capabilities", {"boot_audit": True})
    assert audit.ok is True
    assert audit.to_payload()["data"] == genesis_boot_audit_snapshot()

    galaxy = service.execute("capabilities", {"boot_audit": True, "phase_id": "galaxy"})
    assert galaxy.ok is True
    assert galaxy.to_payload()["data"] == get_genesis_boot_audit_row("galaxy")

    invalid = service.execute("capabilities", {"boot_audit": 1})
    assert invalid.ok is False
    assert invalid.to_payload()["error"]["code"] == "invalid_argument"

    both = service.execute("capabilities", {"boot_audit": True, "export_audit": True})
    assert both.ok is False
    assert both.to_payload()["error"]["code"] == "invalid_argument"
    assert "mutually exclusive" in both.to_payload()["error"]["message"]
