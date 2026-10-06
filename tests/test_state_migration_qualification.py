from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from scripts import check_state_migration_qualification as module


REPO_ROOT = Path(__file__).resolve().parents[1]


def _manifest() -> dict:
    return json.loads(
        (REPO_ROOT / "machine/state_migration_qualification.json").read_text(
            encoding="utf-8"
        )
    )


def _patch_manifest(monkeypatch: pytest.MonkeyPatch, mutated: dict) -> None:
    original = module._load

    def fake_load(root: Path, relative: Path):
        if relative == module.QUALIFICATION:
            return deepcopy(mutated)
        return original(root, relative)

    monkeypatch.setattr(module, "_load", fake_load)


def test_current_state_migration_qualification_is_valid() -> None:
    result = module.validate(REPO_ROOT)

    assert result["status"] == "valid"
    assert result["domain_count"] == 20
    assert result["source_of_truth_domain_count"] == 13
    assert result["scenario_count"] >= 9
    assert result["reference_rehearsal"]["qualified"] is True
    assert len(result["reference_rehearsal"]["receipt_digest"]) == 64


def test_stale_topology_blob_binding_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest()
    manifest["topology_blob_sha"] = "0" * 40
    _patch_manifest(monkeypatch, manifest)

    with pytest.raises(
        module.StateMigrationQualificationError,
        match="stale for the current state topology",
    ):
        module.validate(REPO_ROOT)


def test_missing_domain_qualification_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest()
    manifest["domain_qualification"] = manifest["domain_qualification"][1:]
    _patch_manifest(monkeypatch, manifest)

    with pytest.raises(
        module.StateMigrationQualificationError,
        match="coverage mismatch",
    ):
        module.validate(REPO_ROOT)


def test_planned_evidence_cannot_qualify_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest()
    manifest["domain_qualification"][0]["evidence_refs"] = [
        "planned:future-proof"
    ]
    _patch_manifest(monkeypatch, manifest)

    with pytest.raises(
        module.StateMigrationQualificationError,
        match="cannot be planned evidence",
    ):
        module.validate(REPO_ROOT)


def test_non_authoritative_domain_cannot_claim_authoritative_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest()
    entry = next(
        item
        for item in manifest["domain_qualification"]
        if item["source_of_truth"] is False
    )
    entry["qualification_mode"] = "authoritative-migrate-rollback-restore"
    _patch_manifest(monkeypatch, manifest)

    with pytest.raises(
        module.StateMigrationQualificationError,
        match="non-authoritative state cannot claim authoritative mode",
    ):
        module.validate(REPO_ROOT)


def test_release_gate_drift_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest()
    manifest["release_gate"]["command"] = "true"
    _patch_manifest(monkeypatch, manifest)

    with pytest.raises(
        module.StateMigrationQualificationError,
        match="acceptance gate does not exactly bind",
    ):
        module.validate(REPO_ROOT)


def test_retired_legacy_authority_cannot_be_reintroduced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest()
    original = module._load

    def fake_load(root: Path, relative: Path):
        if relative == module.QUALIFICATION:
            return deepcopy(manifest)
        payload = original(root, relative)
        if relative == module.TOPOLOGY:
            payload = deepcopy(payload)
            payload["physical_stores"].append(
                {
                    "id": "verification-evidence-unbound",
                    "technology": "ghost",
                    "runtime_service": None,
                    "compose_file": None,
                    "volumes": [],
                    "durability": "unbound",
                    "production_role": "ghost",
                    "network": "none",
                    "authentication": "none",
                    "backup": "none",
                    "restore": "none",
                    "migration": "none",
                    "evidence": ["machine/state_topology.json"],
                }
            )
        return payload

    monkeypatch.setattr(module, "_load", fake_load)

    # The source blob binding rejects the topology mutation before a ghost can
    # obtain a release qualification.
    with pytest.raises(
        module.StateMigrationQualificationError,
        match="stale for the current state topology|retired legacy authority",
    ):
        module.validate(REPO_ROOT)
