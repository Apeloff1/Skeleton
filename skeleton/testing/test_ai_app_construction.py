from __future__ import annotations

import json
from pathlib import Path

from scripts.check_ai_app_construction import CONTRACT_PATH, ROOT, validate_construction
from scripts.check_provider_bootstrap import validate_provider_bootstrap


def _contract() -> dict:
    return json.loads((ROOT / CONTRACT_PATH).read_text(encoding="utf-8"))


def test_complete_ai_construction_contract_is_valid() -> None:
    errors, summary = validate_construction(ROOT)

    assert errors == []
    assert summary["ok"] is True
    assert summary["architecture_tag"] == "arch-map/v3.1"
    assert summary["construction_version"] == "3.1.0"
    assert summary["planes"] >= 26
    assert summary["runtime_providers"] == ["openai"]
    assert summary["automation_providers"] == ["repository-automation"]
    assert summary["provider_surfaces"] >= 6


def test_provider_bootstrap_is_fail_closed_and_materialized() -> None:
    contract = _contract()
    bootstrap = contract["provider_bootstrap"]

    assert bootstrap["mandatory"] is True
    assert bootstrap["mode"] == "fail_closed"
    assert bootstrap["runtime_enforcement"]["receipt_required"] is True
    assert bootstrap["runtime_enforcement"]["undeclared_provider_policy"] == "deny"
    assert validate_provider_bootstrap(ROOT) == []


def test_every_partial_plane_has_an_explicit_gap() -> None:
    contract = _contract()
    partial = {plane["id"] for plane in contract["planes"] if plane["state"] == "partial"}
    gap_planes = {
        gap["plane"]
        for gap in contract["gap_register"]
        if gap["status"] == "open"
    }

    assert partial
    assert partial <= gap_planes


def test_p0_gaps_are_explicitly_blocking_sota_completion() -> None:
    contract = _contract()
    p0 = [
        gap
        for gap in contract["gap_register"]
        if gap["priority"] == "P0" and gap["status"] == "open"
    ]

    assert p0
    assert contract["gap_closure_policy"]["p0_gaps_block_sota_complete"] is True
    assert all(gap["construction"] for gap in p0)
    assert all(gap["closure_evidence"] for gap in p0)


def test_construction_phases_cover_each_plane_once() -> None:
    contract = _contract()
    plane_ids = {plane["id"] for plane in contract["planes"]}
    scheduled = [
        plane_id
        for phase in contract["construction_phases"]
        for plane_id in phase["planes"]
    ]

    assert len(scheduled) == len(set(scheduled))
    assert set(scheduled) == plane_ids


def test_provider_documents_all_point_to_canonical_sources() -> None:
    contract = _contract()
    must_read = contract["provider_bootstrap"]["must_read"]

    for entry in contract["provider_bootstrap"]["development_provider_entrypoints"]:
        text = (ROOT / entry["path"]).read_text(encoding="utf-8")
        for relative in must_read:
            assert relative in text


def test_no_required_evidence_path_is_virtual() -> None:
    contract = _contract()

    for plane in contract["planes"]:
        assert (ROOT / plane["owner"]).exists(), plane["id"]
        for relative in plane["evidence"]:
            assert (ROOT / relative).exists(), (plane["id"], relative)


def test_credential_bearing_provider_surfaces_are_declared_and_receipt_gated() -> None:
    contract = _contract()
    credential_surfaces = [
        surface
        for surface in contract["provider_surfaces"]
        if surface["credential_bearing"] is True
    ]

    assert credential_surfaces
    assert {
        surface["owner"]
        for surface in credential_surfaces
    } >= {
        "backend/core/ai_provider.py",
        "skeleton/jeeves/providers.py",
        "skeleton/automation/free_model.py",
    }
    assert all(surface["receipt_required"] is True for surface in credential_surfaces)
    assert all((ROOT / surface["owner"]).is_file() for surface in credential_surfaces)


def test_provider_families_have_one_shared_receipt_contract() -> None:
    contract = _contract()
    enforcement = contract["provider_bootstrap"]["runtime_enforcement"]

    assert enforcement["loader"] == "skeleton/provider_contract.py"
    assert set(enforcement["provider_families"]) == {
        "runtime_model",
        "automation_model",
    }
    assert enforcement["undeclared_provider_policy"] == "deny"
