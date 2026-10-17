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
        return model, {"candidate_status": "candidate_predictive_gain_measured"}
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
