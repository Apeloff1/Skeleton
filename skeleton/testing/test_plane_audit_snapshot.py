"""Regression coverage for the import-free F-15 plane audit snapshot."""

from __future__ import annotations

import json

from skeleton.__main__ import main
from skeleton.application import (
    AUDITED_PLANE_IDS,
    CAPABILITY_MANIFEST_VERSION,
    PLANE_AUDIT_KIND,
    capability_manifest,
    plane_audit_snapshot,
)
from skeleton.organism import __all__ as organism_all
from skeleton.social import __all__ as social_all
from skeleton.galaxy import __all__ as galaxy_all


_ROW_KEYS = {
    "id",
    "module",
    "description",
    "resolvable",
    "public_exports",
    "architecture_exports",
    "export_drift",
    "genesis_wired",
    "genesis_handles",
    "boot_phase_listed",
}


def test_plane_audit_snapshot_is_deterministic_and_import_free(monkeypatch) -> None:
    called = False

    def should_not_import(_module_name: str):
        nonlocal called
        called = True
        raise AssertionError("plane audit must not import capability modules")

    monkeypatch.setattr(
        "skeleton.application.capability_runtime.import_module",
        should_not_import,
    )

    payload = plane_audit_snapshot()
    assert called is False
    assert payload["schema_version"] == CAPABILITY_MANIFEST_VERSION == 1
    assert payload["kind"] == PLANE_AUDIT_KIND == "plane_audit"
    assert [row["id"] for row in payload["planes"]] == list(AUDITED_PLANE_IDS)


def test_plane_audit_rows_lock_public_exports_and_genesis_wiring() -> None:
    payload = plane_audit_snapshot()
    rows = {row["id"]: row for row in payload["planes"]}
    expected_exports = {
        "organism": list(organism_all),
        "social": list(social_all),
        "galaxy": list(galaxy_all),
    }

    for plane_id, expected in expected_exports.items():
        row = rows[plane_id]
        assert set(row) == _ROW_KEYS
        assert row["module"] == f"skeleton.{plane_id}"
        assert row["resolvable"] is True
        assert row["public_exports"] == expected
        assert row["architecture_exports"] == expected
        assert row["export_drift"] == {
            "missing_from_architecture": [],
            "missing_from_public": [],
        }
        assert row["boot_phase_listed"] is False

    assert rows["organism"]["genesis_wired"] is False
    assert rows["social"]["genesis_wired"] is False
    assert rows["organism"]["genesis_handles"] == []
    assert rows["social"]["genesis_handles"] == []

    galaxy = rows["galaxy"]
    assert galaxy["genesis_wired"] is True
    assert galaxy["genesis_handles"] == [
        "kag_sync",
        "galaxy_bridge",
        "galaxy",
        "galaxy_transport",
        "consensus",
        "election",
        "fleet",
        "byzantine",
    ]


def test_plane_audit_does_not_change_identity_manifest() -> None:
    identity = capability_manifest()
    assert "kind" not in identity
    for capability in identity["capabilities"]:
        assert set(capability) == {"id", "module", "description"}


def test_capabilities_cli_plane_audit_matches_python_api(capsys) -> None:
    assert main(["capabilities", "--plane-audit"]) == 0
    assert json.loads(capsys.readouterr().out) == plane_audit_snapshot()


def test_capabilities_cli_rejects_combined_lifecycle_and_plane_audit(capsys) -> None:
    assert main(["capabilities", "--lifecycle", "--plane-audit"]) == 2
    assert "mutually exclusive" in capsys.readouterr().out


def test_http_application_plane_audit_matches_cli_payload() -> None:
    import asyncio

    from skeleton.api import routes

    assert asyncio.run(routes.application_plane_audit()) == plane_audit_snapshot()


def test_shared_command_plane_audit_matches_snapshot_and_stays_fail_closed() -> None:
    from skeleton.application import build_runtime_command_service

    class _State:
        genesis = None

        def is_healthy(self):
            return {"overall": True}

    service = build_runtime_command_service(_State())
    identity = service.execute("capabilities")
    assert identity.ok is True
    assert identity.to_payload()["data"] == capability_manifest()

    audit = service.execute("capabilities", {"plane_audit": True})
    assert audit.ok is True
    assert audit.to_payload()["data"] == plane_audit_snapshot()

    invalid = service.execute("capabilities", {"plane_audit": "yes"})
    assert invalid.ok is False
    assert invalid.to_payload()["error"]["code"] == "invalid_argument"

    both = service.execute("capabilities", {"lifecycle": True, "plane_audit": True})
    assert both.ok is False
    assert both.to_payload()["error"]["code"] == "invalid_argument"
    assert "mutually exclusive" in both.to_payload()["error"]["message"]
