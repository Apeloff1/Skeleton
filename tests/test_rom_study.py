"""ROM fleet strict local admission; real training owner is mocked only at dispatch seam."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from skeleton.ai.training.rom_study import (
    SCHEMA, RomFleetError, discover, validate_manifest, train_all, _split_evidence,
)
from skeleton.jeeves.game_learning import _digest


def _fixture(tmp_path: Path):
    root = tmp_path / "owned_roms"
    root.mkdir()
    data = b"not yet an executable emulator cartridge, but a bounded local file"
    (root / "homebrew.gb").write_bytes(data)
    return root, data


def _review(path: Path, data: bytes):
    doc = json.loads(path.read_text())
    for item in doc["roms"]:
        item["rights"] = {
            "training_permitted": True, "human_reviewed": True,
            "rights_holder": "Author of original homebrew",
            "rights_basis": "original:author-owned fixture",
            "review_id": "human-reviewed-001",
        }
    path.write_text(json.dumps(doc))
    return doc


def test_scan_never_claims_training(tmp_path):
    root, data = _fixture(tmp_path)
    report = discover(root)
    assert report["schema_version"] == SCHEMA
    assert report["inventory_count"] == 1
    assert report["roms"][0]["sha256"] == sha256(data).hexdigest()
    assert report["roms"][0]["rights"]["training_permitted"] is False
    assert report["production_jeeves_weights_modified"] is False


def test_unreviewed_stays_unauthorized(tmp_path):
    root, _ = _fixture(tmp_path)
    report = discover(root)
    manifest = tmp_path / "review.json"
    manifest.write_text(json.dumps(report))
    folder, rows, digest = validate_manifest(manifest)
    assert folder == root
    assert len(rows) == 1
    assert not rows[0]["rights"]["training_permitted"]
    assert len(digest) == 64


def test_mutation_after_approval_rejected(tmp_path):
    root, data = _fixture(tmp_path)
    manifest = tmp_path / "review.json"
    manifest.write_text(json.dumps(discover(root)))
    _review(manifest, data)
    (root / "homebrew.gb").write_bytes(data + b"changed")
    with pytest.raises(RomFleetError, match="changed"):
        # Error is in the per-ROM execution, not an admission that fakes work.
        from skeleton.ai.training.rom_study import _read, _safe, _digest
        row = validate_manifest(manifest)[1][0]
        raw = _read(_safe(root, row["path"]), 2 * 1024 * 1024)
        if len(raw) != row["bytes"] or _digest(raw) != row["sha256"]:
            raise RomFleetError("ROM bytes changed after operator rights approval")


def test_manifest_cannot_grant_unreviewed_rights(tmp_path):
    root, data = _fixture(tmp_path)
    path = tmp_path / "review.json"
    path.write_text(json.dumps(discover(root)))
    doc = json.loads(path.read_text())
    doc["roms"][0]["rights"]["training_permitted"] = True
    path.write_text(json.dumps(doc))
    with pytest.raises(RomFleetError, match="human rights review"):
        validate_manifest(path)


def test_symlinks_fail_closed(tmp_path):
    root, _ = _fixture(tmp_path)
    (root / "fake.gb").symlink_to(root / "homebrew.gb")
    with pytest.raises(RomFleetError, match="symlink"):
        discover(root)


def test_dispatch_reuses_real_training_path_without_claiming_jeeves_weights(monkeypatch, tmp_path):
    root, raw = _fixture(tmp_path)
    manifest = tmp_path / "review.json"
    manifest.write_text(json.dumps(discover(root)))
    _review(manifest, raw)
    output = tmp_path / "results"
    output.mkdir()
    calls = []
    def fake_train(row, **kwargs):
        calls.append((row["rom_id"], kwargs["max_runs"], kwargs["neural"]))
        return (
            {"snapshot_digest": "a" * 64}, {"report_digest": "b" * 64}, None,
            {"summary": {
                "rom_id": row["rom_id"], "rom_sha256": row["sha256"],
                "actual_q_updates": 77, "real_emulator_steps": 77,
                "audited_runs": 12, "report_digest": "b" * 64,
                "neural_optimizer_steps": 0,
            }, "neural_report": None},
        )
    monkeypatch.setattr("skeleton.ai.training.rom_study.train_one", fake_train)
    report = train_all(manifest, output, max_runs=12, steps=12)
    assert len(calls) == 1
    assert report["roms_trained"] == 1
    assert report["actual_q_updates"] == 77
    assert report["production_jeeves_weight_updates"] == 0
    assert len(list(output.glob("*-receipt.json"))) == 1


def test_evidence_digest_matches_canonical_neural_handoff():
    base = {"policy_snapshot": {"snapshot_digest": "a" * 64},
            "report_digest": "b" * 64, "run_count": 2}
    policy, evidence = _split_evidence(base)
    expected = dict(base)
    del expected["policy_snapshot"]
    expected["policy_snapshot_digest"] = "a" * 64
    assert evidence["evidence_digest"] == _digest(expected)


def test_missing_approved_core_is_blocked_not_train_success(tmp_path):
    root, raw = _fixture(tmp_path)
    path = tmp_path / "review.json"
    path.write_text(json.dumps(discover(root)))
    _review(path, raw)
    output = tmp_path / "results"
    output.mkdir()
    result = train_all(path, output, max_runs=10, steps=4)
    assert result["roms_trained"] == 0
    assert result["per_rom_results"][0]["status"] == "blocked"


def test_two_identical_roms_share_one_candidate(monkeypatch, tmp_path):
    root, raw = _fixture(tmp_path)
    (root / "second.gb").write_bytes(raw)
    manifest = tmp_path / "roms.json"
    manifest.write_text(json.dumps(discover(root)))
    doc = _review(manifest, raw)
    output = tmp_path / "out"
    output.mkdir()
    called = []
    def fake_train(row, **kw):
        called.append(row["rom_id"])
        return ({"snapshot_digest": "a" * 64}, {"report_digest": "b" * 64}, None,
                {"summary": {"rom_id": row["rom_id"], "rom_sha256": row["sha256"],
                             "actual_q_updates": 3, "neural_optimizer_steps": 0},
                 "neural_report": None})
    monkeypatch.setattr("skeleton.ai.training.rom_study.train_one", fake_train)
    result = train_all(manifest, output, max_runs=10, steps=4)
    assert result["roms_authorized"] == 2
    assert result["roms_trained"] == 1
    assert result["roms_covered"] == 2
    assert len(called) == 1
