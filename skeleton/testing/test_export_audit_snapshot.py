"""Regression coverage for the import-free manifest export audit."""

from __future__ import annotations

import json

import pytest

from skeleton.__main__ import main
from skeleton.application import (
    CAPABILITIES,
    CAPABILITY_MANIFEST_VERSION,
    EXPORT_AUDIT_KIND,
    capability_manifest,
    export_audit_snapshot,
    get_export_audit_row,
)


_ROW_KEYS = {
    "id",
    "module",
    "description",
    "resolvable",
    "in_architecture_registry",
    "public_export_count",
    "architecture_export_count",
    "export_drift",
}


def test_export_audit_is_import_free(monkeypatch) -> None:
    called = False

    def should_not_import(_module_name: str):
        nonlocal called
        called = True
        raise AssertionError("export audit must not import capability modules")

    monkeypatch.setattr(
        "skeleton.application.capability_runtime.import_module",
        should_not_import,
    )
    payload = export_audit_snapshot()
    assert called is False
    assert payload["schema_version"] == CAPABILITY_MANIFEST_VERSION == 1
    assert payload["kind"] == EXPORT_AUDIT_KIND == "manifest_export_audit"
    assert [row["id"] for row in payload["capabilities"]] == [item.id for item in CAPABILITIES]


def test_export_audit_locks_synced_packages_and_remaining_drift() -> None:
    payload = export_audit_snapshot()
    rows = {row["id"]: row for row in payload["capabilities"]}
    for row in payload["capabilities"]:
        assert set(row) == _ROW_KEYS
        assert row["resolvable"] is True

    for plane_id in ("organism", "social", "galaxy", "application", "content"):
        row = rows[plane_id]
        assert row["in_architecture_registry"] is True
        assert row["export_drift"] == {
            "missing_from_architecture": [],
            "missing_from_public": [],
        }
        assert row["public_export_count"] == row["architecture_export_count"] > 0

    assert rows["cortex"]["export_drift"]["missing_from_architecture"]
    assert rows["gameforge"]["export_drift"]["missing_from_architecture"]
    assert "create_app" in rows["api"]["export_drift"]["missing_from_public"]


def test_capabilities_cli_export_audit_matches_python_api(capsys) -> None:
    assert main(["capabilities", "--export-audit"]) == 0
    assert json.loads(capsys.readouterr().out) == export_audit_snapshot()


def test_http_export_audit_matches_cli_payload() -> None:
    import asyncio

    from fastapi import HTTPException

    from skeleton.api import routes

    snapshot = export_audit_snapshot()
    assert asyncio.run(routes.application_export_audit()) == snapshot

    cortex = asyncio.run(routes.application_export_audit_row(" Cortex "))
    assert cortex == get_export_audit_row("cortex")
    assert cortex["id"] == "cortex"

    with pytest.raises(HTTPException) as missing:
        asyncio.run(routes.application_export_audit_row("missing"))
    assert missing.value.status_code == 404

    with pytest.raises(HTTPException) as empty:
        asyncio.run(routes.application_export_audit_row("   "))
    assert empty.value.status_code == 422


def test_shared_command_export_audit_matches_snapshot_and_stays_fail_closed() -> None:
    from skeleton.application import build_runtime_command_service

    class _State:
        genesis = None

        def is_healthy(self):
            return {"overall": True}

    service = build_runtime_command_service(_State())
    identity = service.execute("capabilities")
    assert identity.ok is True
    assert identity.to_payload()["data"] == capability_manifest()

    audit = service.execute("capabilities", {"export_audit": True})
    assert audit.ok is True
    assert audit.to_payload()["data"] == export_audit_snapshot()

    row = service.execute("capabilities", {"export_audit": True, "capability_id": "galaxy"})
    assert row.ok is True
    assert row.to_payload()["data"] == get_export_audit_row("galaxy")

    invalid = service.execute("capabilities", {"export_audit": "yes"})
    assert invalid.ok is False
    assert invalid.to_payload()["error"]["code"] == "invalid_argument"

    both = service.execute("capabilities", {"export_audit": True, "lifecycle": True})
    assert both.ok is False
    assert both.to_payload()["error"]["code"] == "invalid_argument"
