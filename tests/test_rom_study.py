"""ROM-wide training: local inventory, rights gates and replay-evidence integrity."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from skeleton.ai.training import rom_study as rom
from skeleton.jeeves.game_learning import _digest


def _roms(tmp_path: Path):
    root = tmp_path / "roms"
    root.mkdir()
    first = root / "a.gb"
    first.write_bytes(b"original homebrew rom example only" * 2)
    second = root / "b.nes"
    second.write_bytes(b"second original test game")
    (root / "ignore.txt").write_text("not a ROM")
    (root / "link.gb").symlink_to(first)
    return root, first, second


def _approvals(tmp_path: Path, item: Path, *, permitted: bool = True):
    digest = hashlib.sha256(item.read_bytes()).hexdigest()
    row = {
        "sha256": digest,
        "content_size_bytes": item.stat().st_size,
        "target_id": "game_boy",
        "core_id": "gambatte",
        "rights": {
            "rights_holder": "Original test author",
            "rights_basis": "original:authored-test-only",
            "review_id": "human-review-001",
            "human_reviewed": permitted,
            "training_permitted": permitted,
        },
    }
    output = tmp_path / "approvals.json"
    output.write_text(json.dumps({
        "schema_version": rom.APPROVAL_SCHEMA,
        "roms": [row],
    }))
    return output, row


def test_inventory_page_deterministic_and_symlinks_not_followed(tmp_path):
    root, first, second = _roms(tmp_path)
    first_page = rom.inventory_page(root, limit=1)
    assert first_page["total_candidate_files"] == 2
    assert len(first_page["rows"]) == 1
    assert first_page["rows"][0]["relative_path"] == "a.gb"
    assert first_page["rows"][0]["file_sha256"] == hashlib.sha256(first.read_bytes()).hexdigest()
    assert first_page["next_cursor"] == "a.gb"
    assert first_page["rows"][0]["authorized_for_training"] is False
    second_page = rom.inventory_page(root, cursor=first_page["next_cursor"], limit=1)
    assert [r["relative_path"] for r in second_page["rows"]] == ["b.nes"]
    assert second_page["finished"] is True
    assert second_page["next_cursor"] is None
    assert second_page["rows"][0]["file_sha256"] == hashlib.sha256(second.read_bytes()).hexdigest()


def test_inventory_rejects_symlinked_root(tmp_path):
    root, _, _ = _roms(tmp_path)
    link = tmp_path / "library_link"
    link.symlink_to(root, target_is_directory=True)
    with pytest.raises(rom.RomStudyError, match="symlinks"):
        rom.inventory_page(link)


def test_inventory_rejects_bad_page_and_cursor(tmp_path):
    root, _, _ = _roms(tmp_path)
    with pytest.raises(rom.RomStudyError, match="page size"):
        rom.inventory_page(root, limit=129)
    with pytest.raises(rom.RomStudyError, match="continuation"):
        rom.inventory_page(root, cursor="../private-file")


def test_training_rights_cannot_be_inferred(tmp_path):
    root, first, _ = _roms(tmp_path)
    output = tmp_path / "receipts"
    output.mkdir(mode=0o700)
    rights = tmp_path / "approvals.json"
    rights.write_text(json.dumps({
        "schema_version": rom.APPROVAL_SCHEMA, "roms": [],
    }))
    report = rom.train_page(root, rights, output, limit=2, runs=1)
    assert report["q_policy_training_completed"] == 0
    assert report["blocked_or_unreviewed"] == 2
    assert all(row["state"] == "no_training_rights_review"
               for row in report["page_results"])
    assert not list(output.glob("*.json"))


def test_explicit_review_is_required(tmp_path):
    _, first, _ = _roms(tmp_path)
    approvals, _ = _approvals(tmp_path, first, permitted=False)
    with pytest.raises(rom.RomStudyError, match="unapproved"):
        rom._load_approvals(approvals)


def _fake_training(tmp_path, monkeypatch, *, updates: int):
    """Stub only native execution; exercise real inventory, rights, batch and receipt code."""
    from skeleton.jeeves import game_emulator_catalog as catalog
    from skeleton.jeeves import game_emulator_training_lab as lab

    core = SimpleNamespace(
        core_id="gambatte", target_ids=("game_boy",),
    )
    registry = SimpleNamespace(
        registry_digest="a" * 64,
        resolve_core=lambda name: core if name == "gambatte" else None,
    )
    monkeypatch.setattr(catalog.GameEmulatorRegistry, "from_environment",
                        classmethod(lambda cls: registry))
    monkeypatch.setattr(catalog, "emulator_content_admission",
                        lambda name: {"admitted_entrypoint_extensions": [".gb"]})
    prepared = SimpleNamespace(
        as_dict=lambda: {
            "root": str(tmp_path), "entrypoint": "a.gb",
            "files": [{"name": "a.gb", "size_bytes": 1, "sha256": "b" * 64}],
            "content_digest": "c" * 64,
        },
        close=lambda: None,
    )
    monkeypatch.setattr(rom, "_content_for_training", lambda *a, **k: prepared)
    captured = []
    def fake_training(request, *, source_lineage, config, policy_id, cancel=None):
        captured.append((request, source_lineage))
        original = {
            "policy_snapshot": {"snapshot_digest": "d" * 64},
            "environment": {"environment_digest": "f" * 64},
            "actual_q_table_updates": updates,
            "actual_training_steps": 6,
            "actual_neural_parameter_updates": 0,
        }
        return {**original, "report_digest": _digest(original)}
    monkeypatch.setattr(lab, "run_emulator_training_lab", fake_training)
    return captured


@pytest.mark.parametrize("updates,expected", [
    (2, "q_policy_updated_with_receipt"),
    (0, "q_policy_executed_no_updates"),
])
def test_batch_uses_existing_lab_and_distinguishes_real_updates(
    tmp_path, monkeypatch, updates, expected
):
    root, first, _ = _roms(tmp_path)
    approvals, _ = _approvals(tmp_path, first)
    out = tmp_path / "receipts"
    out.mkdir(mode=0o700)
    called = _fake_training(tmp_path, monkeypatch, updates=updates)
    result = rom.train_page(root, approvals, out, limit=2, runs=1, steps=4)
    row = next(r for r in result["page_results"] if r["relative_path"] == "a.gb")
    assert row["state"] == expected
    assert row["actual_q_table_updates"] == updates
    assert len(called) == 1
    assert called[0][0].kind == "libretro"
    assert called[0][1]["rights_acknowledged"] is True
    assert result["actual_jeeves_weight_training"] is False
    receipts = list(out.glob("rom-*.json"))
    assert len(receipts) == 1
    identity = hashlib.sha256(first.read_bytes()).hexdigest()
    checked = rom.verified_rom_receipt(receipts[0], expected_source_sha256=identity)
    assert checked["actual_q_table_updates"] == updates
    # Existing identical receipt is independently checked before skipping.
    later = rom.train_page(root, approvals, out, limit=2, runs=1, steps=4)
    prior = next(r for r in later["page_results"] if r["relative_path"] == "a.gb")
    assert prior["state"] == "previous_verified_receipt_no_reexecution"
    assert len(called) == 1


def test_corrupted_existing_receipt_fails_closed(tmp_path, monkeypatch):
    root, first, _ = _roms(tmp_path)
    approvals, _ = _approvals(tmp_path, first)
    out = tmp_path / "receipts"
    out.mkdir(mode=0o700)
    _fake_training(tmp_path, monkeypatch, updates=1)
    rom.train_page(root, approvals, out, runs=1, steps=4)
    receipt = next(out.glob("rom-*.json"))
    original = json.loads(receipt.read_text())
    original["candidate_evidence"]["actual_q_table_updates"] = 999
    receipt.write_text(json.dumps(original) + "\n")
    result = rom.train_page(root, approvals, out, runs=1, steps=4)
    item = next(r for r in result["page_results"] if r["relative_path"] == "a.gb")
    assert item["state"] == "emulator_training_blocked"
    assert item["failure_type"] == "RomStudyError"
    assert result["q_policy_training_completed"] == 0



def test_optional_neural_candidate_actual_optimizer_seam(tmp_path, monkeypatch):
    """Native emulator is mocked, but the neural optimizer seam is exercised."""
    root, first, _ = _roms(tmp_path)
    approvals, _ = _approvals(tmp_path, first)
    output = tmp_path / "receipts"
    output.mkdir(mode=0o700)
    _fake_training(tmp_path, monkeypatch, updates=3)
    from skeleton.jeeves import game_emulator_neural_world as neural

    trained = []
    model = {"model_digest": "e" * 64, "real_optimizer_steps": 4}
    def fake_optimizer(evidence, policy, *, config, cancel=None):
        trained.append((evidence, policy, config))
        model.update({
            "source_evidence_digest": evidence["report_digest"],
            "source_policy_snapshot_digest": policy["snapshot_digest"],
            "source_environment_digest": evidence["environment"]["environment_digest"],
            "measured_predictive_gate": "candidate_predictive_gain_measured",
        })
        report = {
            "parent_emulator_evidence_digest": evidence["report_digest"],
            "candidate_status": "candidate_predictive_gain_measured",
            "world_model_digest": model["model_digest"],
            "real_neural_optimizer_steps": model["real_optimizer_steps"],
            "production_model_promotion": False,
        }
        report["report_digest"] = _digest(report)
        return model, report
    monkeypatch.setattr(neural, "train_neural_world_from_evidence", fake_optimizer)
    monkeypatch.setattr(neural, "validate_neural_world_checkpoint", lambda value: None)
    result = rom.train_page(root, approvals, output, steps=4, runs=1,
                            neural_world=True, neural_epochs=3, neural_width=8)
    item = next(x for x in result["page_results"] if x["relative_path"] == "a.gb")
    assert item["state"] == "q_policy_updated_with_receipt"
    assert item["neural_world_status"] == "candidate_trained_requires_independent_review"
    assert item["neural_candidate_optimizer_steps"] == 4
    assert result["neural_candidate_training_completed"] == 1
    assert len(trained) == 1
    assert trained[0][0]["policy_snapshot_digest"] == "d" * 64
    receipt = next(output.glob("rom-*.json"))
    checked = rom.verified_rom_receipt(
        receipt, expected_source_sha256=hashlib.sha256(first.read_bytes()).hexdigest()
    )
    assert checked["neural_weights_updated"] == 0


def test_neural_rejection_preserves_q_evidence(tmp_path, monkeypatch):
    root, first, _ = _roms(tmp_path)
    approvals, _ = _approvals(tmp_path, first)
    output = tmp_path / "receipts"
    output.mkdir(mode=0o700)
    _fake_training(tmp_path, monkeypatch, updates=2)
    from skeleton.jeeves import game_emulator_neural_world as neural
    def reject(*args, **kwargs):
        raise neural.EmulatorNeuralError("insufficient independent replay episodes")
    monkeypatch.setattr(neural, "train_neural_world_from_evidence", reject)
    result = rom.train_page(root, approvals, output, steps=4, runs=1, neural_world=True)
    item = next(x for x in result["page_results"] if x["relative_path"] == "a.gb")
    assert item["state"] == "q_policy_updated_with_receipt"
    assert item["neural_world_status"] == "candidate_training_blocked"
    assert item["neural_candidate_optimizer_steps"] == 0
    assert result["neural_candidate_training_completed"] == 0
    assert result["q_policy_training_completed"] == 1



def test_frozen_inventory_pins_only_hashes_and_pages_without_full_rescan(
    tmp_path, monkeypatch
):
    from skeleton.ai.training import rom_inventory_snapshot as frozen
    root, first, second = _roms(tmp_path)
    destination = tmp_path / "frozen"
    destination.mkdir(mode=0o700)
    receipt = frozen.freeze_rom_inventory(root, destination)
    assert receipt["file_count"] == 2
    snap = frozen.load_frozen_inventory(Path(receipt["manifest_path"]), root=root)
    assert all("data" not in row and "bytes" not in row for row in snap["entries"])
    first_page = frozen.frozen_inventory_page(snap, root=root, limit=1)
    assert first_page["rows"][0]["relative_path"] == "a.gb"
    second_page = frozen.frozen_inventory_page(
        snap, root=root, cursor=first_page["next_cursor"], limit=1
    )
    assert second_page["rows"][0]["relative_path"] == "b.nes"
    assert second_page["finished"] is True
    assert second_page["frozen_inventory_sha256"] == snap["inventory_sha256"]
    with pytest.raises(rom.RomStudyError, match="already exists"):
        frozen.freeze_rom_inventory(root, destination)
    first.write_bytes(b"changed ROM source bytes")
    altered = frozen.frozen_inventory_page(snap, root=root, limit=1)
    assert altered["rows"][0]["state"] == "identity_unavailable"
    assert altered["rows"][0]["emulator_execution_checked"] is False


def test_tampered_snapshot_manifest_rejected(tmp_path):
    from skeleton.ai.training import rom_inventory_snapshot as frozen
    root, first, second = _roms(tmp_path)
    destination = tmp_path / "frozen"
    destination.mkdir(mode=0o700)
    receipt = frozen.freeze_rom_inventory(root, destination)
    manifest = Path(receipt["manifest_path"])
    raw = json.loads(manifest.read_text())
    raw["entries"][0]["file_sha256"] = "e" * 64
    manifest.write_text(json.dumps(raw) + "\n")
    with pytest.raises(rom.RomStudyError, match="checksum"):
        frozen.load_frozen_inventory(manifest, root=root)


def test_training_from_frozen_snapshot_rejects_replaced_rom(tmp_path):
    from skeleton.ai.training import rom_inventory_snapshot as frozen
    root, first, _ = _roms(tmp_path)
    destination = tmp_path / "frozen"
    destination.mkdir(mode=0o700)
    receipt = frozen.freeze_rom_inventory(root, destination)
    snap = frozen.load_frozen_inventory(Path(receipt["manifest_path"]), root=root)
    approvals, _ = _approvals(tmp_path, first)
    first.write_bytes(b"modified content which lacks the pinned SHA")
    result = rom.train_page(root, approvals, destination, runs=1,
                            inventory_snapshot=snap)
    row = next(x for x in result["page_results"] if x["relative_path"] == "a.gb")
    assert row["state"] == "source_identity_unavailable"
    assert result["q_policy_training_completed"] == 0



def test_exact_disc_companion_rights_and_hash_binding(tmp_path, monkeypatch):
    from skeleton.jeeves import game_emulator_catalog as catalog
    from skeleton.jeeves import game_emulator_host as host
    from skeleton.jeeves import game_emulator_training_lab as lab
    from skeleton.jeeves.game_emulator_operator_content import operator_directory_content
    from types import SimpleNamespace

    root = tmp_path / "library"
    game = root / "original_disc"
    game.mkdir(parents=True)
    cue = game / "original_disc.cue"
    cue.write_text('FILE "track01.bin" BINARY\n  TRACK 01 MODE1/2352\n'
                   '    INDEX 01 00:00:00\n')
    companion = game / "track01.bin"
    companion.write_bytes(b"homebrew original disc sectors" * 1024)
    bundle, reader = operator_directory_content(game, cue.name)
    entry = bundle.files[cue.name]
    assert entry.sha256 == hashlib.sha256(cue.read_bytes()).hexdigest()
    approved_digest = bundle.bundle_digest
    approval = {
        "sha256": entry.sha256, "bundle_sha256": approved_digest,
        "content_size_bytes": cue.stat().st_size,
        "target_id": "ps1", "core_id": "swanstation",
        "rights": {
            "rights_holder": "Original example author",
            "rights_basis": "original:homebrew-disc-and-companions",
            "review_id": "independent-disc-review",
            "training_permitted": True, "human_reviewed": True,
        },
    }
    approved = tmp_path / "rights.json"
    approved.write_text(json.dumps({
        "schema_version": rom.APPROVAL_SCHEMA, "roms": [approval],
    }))
    out = tmp_path / "receipts"
    out.mkdir(mode=0o700)
    core = SimpleNamespace(core_id="swanstation", target_ids=("ps1",))
    registry = SimpleNamespace(
        registry_digest="a" * 64,
        resolve_core=lambda ident: core,
    )
    monkeypatch.setattr(catalog.GameEmulatorRegistry, "from_environment",
                        classmethod(lambda cls: registry))
    monkeypatch.setattr(catalog, "emulator_content_admission",
                        lambda ident: {"admitted_entrypoint_extensions": [".cue"]})
    seen = []
    def fake_prepare(actual_bundle, *, reader=None):
        assert actual_bundle.bundle_digest == approved_digest
        assert reader is not None
        seen.append(actual_bundle)
        return SimpleNamespace(
            as_dict=lambda: {
                "root": str(out), "entrypoint": cue.name,
                "files": [{"name": cue.name, "size_bytes": cue.stat().st_size,
                           "sha256": entry.sha256}],
                "content_digest": approved_digest,
            },
            close=lambda: None,
        )
    monkeypatch.setattr(host, "prepare_emulator_content", fake_prepare)
    from skeleton.jeeves.game_learning import _digest
    def fake_training(request, *, source_lineage, config, policy_id, cancel=None):
        assert source_lineage["content_bundle_sha256"] == approved_digest
        receipt = {"policy_snapshot": {"snapshot_digest": "d" * 64},
                   "actual_q_table_updates": 2, "actual_training_steps": 2,
                   "actual_neural_parameter_updates": 0}
        return {**receipt, "report_digest": _digest(receipt)}
    monkeypatch.setattr(lab, "run_emulator_training_lab", fake_training)
    result = rom.train_page(root, approved, out, runs=1, steps=4)
    first = next(item for item in result["page_results"]
                 if item["relative_path"] == "original_disc/original_disc.cue")
    assert first["state"] == "q_policy_updated_with_receipt"
    assert len(seen) == 1
    # Companion change must invalidate the approved whole-disc binding,
    # even when the entrypoint CUE bytes remain identical.
    companion.write_bytes(b"modified homebrew sectors" * 1024)
    second = rom.train_page(root, approved, out, runs=1, steps=4)
    changed = next(item for item in second["page_results"]
                   if item["relative_path"] == "original_disc/original_disc.cue")
    assert changed["state"] == "emulator_training_blocked"
    assert "disc companion bundle differs" in changed["failure_reason"]
    assert len(seen) == 1


def test_disc_approval_cannot_omit_companion_digest(tmp_path):
    from skeleton.jeeves.game_emulator_operator_content import operator_directory_content
    root = tmp_path / "disc"
    root.mkdir()
    (root / "test.cue").write_text('FILE "test.bin" BINARY\n  TRACK 01 MODE1/2352\n'
                                   '    INDEX 01 00:00:00\n')
    (root / "test.bin").write_bytes(b"a" * 2352)
    bundle, reader = operator_directory_content(root, "test.cue")
    assert bundle.bundle_digest
    assert len(bundle.files) == 2



def test_fleet_audit_rights_pending_and_duplicate_not_counted(tmp_path):
    from skeleton.ai.training.rom_inventory_snapshot import freeze_rom_inventory
    from skeleton.ai.training.rom_fleet_audit import audit_fleet_page
    root, first, _ = _roms(tmp_path)
    (root / "duplicate.gb").write_bytes(first.read_bytes())
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    frozen = freeze_rom_inventory(root, private)
    approvals = private / "approvals.json"
    approvals.write_text(json.dumps({
        "schema_version": rom.APPROVAL_SCHEMA,
        "roms": [],
    }))
    report = audit_fleet_page(
        root, Path(frozen["manifest_path"]), approvals, private,
    )
    counts = report["page_counts"]
    assert counts["candidate_files"] == 3
    assert counts["distinct_sources_in_page"] == 2
    assert counts["duplicates_not_retrained"] == 1
    assert counts["rights_review_required"] == 2
    assert counts["verified_q_policy_sources"] == 0
    assert report["production_jeeves_weights_modified"] is False


def test_fleet_audit_verifies_matching_approval_and_snapshot(tmp_path, monkeypatch):
    from skeleton.ai.training.rom_inventory_snapshot import (
        freeze_rom_inventory, load_frozen_inventory,
    )
    from skeleton.ai.training.rom_fleet_audit import audit_fleet_page
    root, first, _ = _roms(tmp_path)
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    freeze = freeze_rom_inventory(root, private)
    snapshot = load_frozen_inventory(Path(freeze["manifest_path"]), root=root)
    approvals, _ = _approvals(tmp_path, first)
    _fake_training(tmp_path, monkeypatch, updates=4)
    measured = rom.train_page(
        root, approvals, private, limit=2,
        inventory_snapshot=snapshot, runs=1, steps=4,
    )
    assert measured["q_policy_training_completed"] == 1
    report = audit_fleet_page(
        root, Path(freeze["manifest_path"]), approvals, private, limit=2,
    )
    assert report["page_counts"]["verified_q_policy_sources"] == 1
    assert report["page_counts"]["rights_review_required"] == 1
    assert report["source_execution_coverage_pct"] == 50.0
    row = next(item for item in report["rows"] if item["relative_path"] == "a.gb")
    assert row["status"] == "verified_q_policy_updated"
    assert row["max_q_updates_single_run"] == 4
    assert row["neural_candidate_trained"] is False
    # The receipt existed, but updated approval is not silently accepted.
    approvals.write_text(json.dumps({
        "schema_version": rom.APPROVAL_SCHEMA,
        "roms": [],
    }))
    changed = audit_fleet_page(
        root, Path(freeze["manifest_path"]), approvals, private,
    )
    assert changed["page_counts"]["verified_q_policy_sources"] == 0


def test_fleet_audit_rejects_tampered_receipt(tmp_path, monkeypatch):
    from skeleton.ai.training.rom_inventory_snapshot import (
        freeze_rom_inventory, load_frozen_inventory,
    )
    from skeleton.ai.training.rom_fleet_audit import audit_fleet_page
    root, first, _ = _roms(tmp_path)
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    freeze = freeze_rom_inventory(root, private)
    snap = load_frozen_inventory(Path(freeze["manifest_path"]), root=root)
    approvals, _ = _approvals(tmp_path, first)
    _fake_training(tmp_path, monkeypatch, updates=3)
    rom.train_page(root, approvals, private, runs=1, steps=4,
                   inventory_snapshot=snap)
    receipt = next(private.glob("rom-*.json"))
    payload = json.loads(receipt.read_text())
    payload["candidate_evidence"]["actual_q_table_updates"] = 9000
    receipt.write_text(json.dumps(payload) + "\n")
    report = audit_fleet_page(
        root, Path(freeze["manifest_path"]), approvals, private,
    )
    assert report["page_counts"]["verified_q_policy_sources"] == 0
    assert report["page_counts"]["invalid_or_stale_receipt_sources"] == 1
    assert report["production_jeeves_weights_modified"] is False



def test_fleet_audit_rejects_falsified_neural_optimizer_receipt(tmp_path, monkeypatch):
    from skeleton.ai.training.rom_inventory_snapshot import (
        freeze_rom_inventory, load_frozen_inventory,
    )
    from skeleton.ai.training.rom_fleet_audit import audit_fleet_all
    from skeleton.jeeves import game_emulator_neural_world as neural
    root, first, _ = _roms(tmp_path)
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    receipt = freeze_rom_inventory(root, private)
    snap = load_frozen_inventory(Path(receipt["manifest_path"]), root=root)
    approvals, _ = _approvals(tmp_path, first)
    _fake_training(tmp_path, monkeypatch, updates=3)
    model = {"model_digest": "c" * 64, "real_optimizer_steps": 4}
    def optimizer(evidence, policy, *, config, cancel=None):
        model.update({
            "source_evidence_digest": evidence["report_digest"],
            "source_policy_snapshot_digest": policy["snapshot_digest"],
            "source_environment_digest": evidence["environment"]["environment_digest"],
            "measured_predictive_gate": "candidate_predictive_gain_measured",
        })
        report = {
            "parent_emulator_evidence_digest": evidence["report_digest"],
            "candidate_status": "candidate_predictive_gain_measured",
            "world_model_digest": model["model_digest"],
            "real_neural_optimizer_steps": 4,
            "production_model_promotion": False,
        }
        report["report_digest"] = _digest(report)
        return model, report
    monkeypatch.setattr(neural, "train_neural_world_from_evidence", optimizer)
    monkeypatch.setattr(neural, "validate_neural_world_checkpoint", lambda candidate: None)
    rom.train_page(root, approvals, private, inventory_snapshot=snap,
                   runs=1, steps=4, neural_world=True)
    check = audit_fleet_all(
        root, Path(receipt["manifest_path"]), approvals, private,
    )
    assert check["totals"]["verified_neural_candidate_sources"] == 1
    record_path = next(private.glob("rom-*.json"))
    record = json.loads(record_path.read_text())
    record["neural_world"]["training_report"]["real_neural_optimizer_steps"] = 9999
    record_path.write_text(json.dumps(record) + "\n")
    invalid = audit_fleet_all(
        root, Path(receipt["manifest_path"]), approvals, private,
    )
    assert invalid["totals"]["verified_neural_candidate_sources"] == 0
    assert invalid["totals"]["verified_q_policy_sources"] == 0
    assert invalid["totals"]["invalid_or_stale_receipt_sources"] == 1



def test_fleet_audit_hardware_core_coverage_and_alias_deduplication(
    tmp_path, monkeypatch
):
    from skeleton.ai.training.rom_inventory_snapshot import (
        freeze_rom_inventory, load_frozen_inventory,
    )
    from skeleton.ai.training.rom_fleet_audit import audit_fleet_all

    root, first, _ = _roms(tmp_path)
    (root / "same-source.gb").write_bytes(first.read_bytes())
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    inventory = freeze_rom_inventory(root, private)
    frozen = load_frozen_inventory(Path(inventory["manifest_path"]), root=root)
    approvals, _ = _approvals(tmp_path, first)
    _fake_training(tmp_path, monkeypatch, updates=4)

    rom.train_page(
        root, approvals, private, steps=4, runs=1, inventory_snapshot=frozen,
    )
    full = audit_fleet_all(
        root, Path(inventory["manifest_path"]), approvals, private, limit=1,
    )
    groups = full["by_hardware_core"]
    assert len(groups) == 1
    assert groups[0]["target_id"] == "game_boy"
    assert groups[0]["core_id"] == "gambatte"
    assert groups[0]["rights_approved_unique_sources"] == 1
    assert groups[0]["verified_q_policy_updated_sources"] == 1
    assert groups[0]["verified_execution_coverage_pct"] == 100.0
    assert groups[0]["neural_candidate_coverage_pct"] == 0.0
    assert full["totals"]["duplicates_not_retrained"] == 1
    assert full["totals"]["distinct_sources_in_page"] == 2
    assert full["source_execution_coverage_pct"] == 50.0
    assert full["production_jeeves_weights_modified"] is False



def test_fleet_neural_candidate_cross_source_mismatch_fails_closed(
    tmp_path, monkeypatch
):
    from skeleton.ai.training.rom_inventory_snapshot import (
        freeze_rom_inventory, load_frozen_inventory,
    )
    from skeleton.ai.training.rom_fleet_audit import audit_fleet_all
    from skeleton.jeeves import game_emulator_neural_world as neural
    root, first, _ = _roms(tmp_path)
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    snapshot_receipt = freeze_rom_inventory(root, private)
    snap = load_frozen_inventory(
        Path(snapshot_receipt["manifest_path"]), root=root,
    )
    approvals, _ = _approvals(tmp_path, first)
    _fake_training(tmp_path, monkeypatch, updates=3)
    model = {"model_digest": "c" * 64, "real_optimizer_steps": 4}
    def optimizer(evidence, policy, *, config, cancel=None):
        model.update({
            "source_evidence_digest": evidence["report_digest"],
            "source_policy_snapshot_digest": policy["snapshot_digest"],
            "source_environment_digest": evidence["environment"]["environment_digest"],
            "measured_predictive_gate": "candidate_predictive_gain_measured",
        })
        report = {
            "world_model_digest": model["model_digest"],
            "parent_emulator_evidence_digest": evidence["report_digest"],
            "real_neural_optimizer_steps": 4,
            "candidate_status": "candidate_predictive_gain_measured",
            "production_model_promotion": False,
        }
        report["report_digest"] = _digest(report)
        return model, report
    monkeypatch.setattr(neural, "train_neural_world_from_evidence", optimizer)
    monkeypatch.setattr(neural, "validate_neural_world_checkpoint", lambda model: None)
    rom.train_page(root, approvals, private, inventory_snapshot=snap,
                   runs=1, steps=4, neural_world=True)
    before = audit_fleet_all(
        root, Path(snapshot_receipt["manifest_path"]), approvals, private,
    )
    assert before["totals"]["verified_neural_candidate_sources"] == 1
    receipt = next(private.glob("rom-*.json"))
    document = json.loads(receipt.read_text())
    # Even a structurally valid and self-consistent candidate from a different
    # policy snapshot is not admissible under this ROM's source evidence.
    document["neural_world"]["neural_model"]["source_policy_snapshot_digest"] = "a" * 64
    receipt.write_text(json.dumps(document) + "\n")
    rejected = audit_fleet_all(
        root, Path(snapshot_receipt["manifest_path"]), approvals, private,
    )
    assert rejected["totals"]["verified_q_policy_sources"] == 0
    assert rejected["totals"]["verified_neural_candidate_sources"] == 0
    assert rejected["totals"]["invalid_or_stale_receipt_sources"] == 1



def test_frozen_inventory_large_cursor_does_not_rebuild_full_name_list(tmp_path, monkeypatch):
    """Cursor lookups must be logarithmic, not one full scan per page."""
    from skeleton.ai.training import rom_inventory_snapshot as frozen

    class NoLinearIteration(list):
        def __iter__(self):
            raise AssertionError("frozen inventory paging iterated all ROM names")

    root = tmp_path / "library"
    root.mkdir()
    rows = NoLinearIteration([
        {
            "relative_path": f"{i:05d}.gb", "file_sha256": "a" * 64,
            "size_bytes": 17, "extension": ".gb",
        }
        for i in range(16384)
    ])
    snapshot = {
        "schema_version": frozen.SCHEMA,
        "root": str(root),
        "entries": rows,
        "inventory_sha256": "b" * 64,
    }
    monkeypatch.setattr(frozen, "_stream_identity",
                        lambda path, expected=None: (expected, 17, b""))
    result = frozen.frozen_inventory_page(
        snapshot, root=root, cursor="15000.gb", limit=2,
    )
    assert [r["relative_path"] for r in result["rows"]] == [
        "15001.gb", "15002.gb",
    ]
    assert result["next_cursor"] == "15002.gb"
    assert result["total_candidate_files"] == 16384


def test_fleet_audit_reuses_canonical_index_across_pages(tmp_path, monkeypatch):
    from skeleton.ai.training import rom_fleet_audit as audit
    from skeleton.ai.training.rom_inventory_snapshot import freeze_rom_inventory

    root, _, _ = _roms(tmp_path)
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    snapshot = freeze_rom_inventory(root, private)
    approvals = private / "rights.json"
    approvals.write_text(json.dumps({
        "schema_version": rom.APPROVAL_SCHEMA,
        "roms": [],
    }))
    actual_index = audit._source_index
    calls = []
    def recorded_index(frozen):
        calls.append(len(frozen["entries"]))
        return actual_index(frozen)
    monkeypatch.setattr(audit, "_source_index", recorded_index)
    result = audit.audit_fleet_all(
        root, Path(snapshot["manifest_path"]), approvals, private, limit=1,
    )
    assert result["pages_audited"] == 2
    assert result["totals"]["rights_review_required"] == 2
    assert calls == [2]
