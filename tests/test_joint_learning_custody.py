"""Real filesystem ROM inventory + validated SDK manifest drift, no execution.

An accounting checkpoint never grants ROM/SDK rights or updates any AI model.
"""
from __future__ import annotations

import json

from skeleton.ai.training.joint_learning_custody import audit_joint_learning_custody
from skeleton.ai.training.rom_inventory_snapshot import freeze_rom_inventory
from skeleton.ai.training.rom_study import APPROVAL_SCHEMA
from tests.test_sdk_custody_drift import build, fixture


def _rom_fixture(tmp_path):
    root = tmp_path / "original-roms"
    root.mkdir()
    (root / "homebrew.gb").write_bytes(b"test-owned-game" * 3)
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    manifest = freeze_rom_inventory(root, private)
    approvals = private / "rights.json"
    approvals.write_text(json.dumps({"schema_version": APPROVAL_SCHEMA, "roms": []}))
    return root, private, manifest, approvals


def _assess(before, after, tmp_path, **kwargs):
    root, private, frozen, approvals = _rom_fixture(tmp_path)
    return audit_joint_learning_custody(
        before, after,
        rom_root=root,
        frozen_inventory=__import__("pathlib").Path(frozen["manifest_path"]),
        rom_approvals=approvals, rom_receipts=private,
        page_limit=1, **kwargs,
    )


def test_rights_pending_is_not_false_reported_as_unified_model_training(tmp_path):
    before = build({"a" * 64: fixture()})
    report = _assess(before, before, tmp_path)
    assert report["status"] == "cross_source_license_review_required"
    assert report["rom"]["rights_review_required"] == 1
    assert report["rom"]["verified_q_policy_source_claims"] == 0
    assert report["sdk"]["changed_documents"] == 0
    assert report["automatic_weight_promotion_authorized"] is False
    assert report["actual_jeeves_speaking_model_weight_updates"] == 0
    assert report["raw_sdk_corpus_or_rom_content_included"] is False
    assert len(report["custody_digest"]) == 64


def test_sdk_revocation_with_rom_rights_pending_requires_both_reviews(tmp_path):
    previous = build({"a" * 64: fixture()})
    revoked = build({"a" * 64: fixture(trainable=False)})
    report = _assess(previous, revoked, tmp_path)
    assert report["status"] == "cross_source_license_review_required"
    assert report["sdk"]["changed_documents"] == 1
    assert report["sdk"]["review_required"] is True
    assert report["rom"]["rights_review_required"] == 1
    assert report["open_review_conditions_in_audited_scope"] == 2


def test_partially_paged_fleet_cannot_be_reported_as_qualified(tmp_path):
    before = build({"a" * 64: fixture()})
    root = tmp_path / "roms"
    root.mkdir()
    for number in range(3):
        (root / f"homebrew-{number}.gb").write_bytes(f"owned-original-{number}".encode())
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    frozen = freeze_rom_inventory(root, private)
    rights = private / "rights.json"
    rights.write_text(json.dumps({"schema_version": APPROVAL_SCHEMA, "roms": []}))
    report = audit_joint_learning_custody(
        before, before, rom_root=root,
        frozen_inventory=__import__("pathlib").Path(frozen["manifest_path"]),
        rom_approvals=rights, rom_receipts=private,
        page_limit=1, max_pages=1,
    )
    assert report["status"] == "fleet_page_horizon_incomplete"
    assert report["rom"]["finished_inventory"] is False
    assert report["automatic_weight_promotion_authorized"] is False
