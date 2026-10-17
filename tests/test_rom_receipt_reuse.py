"""ROM batch reuse must revalidate Q evidence, not trust an existing filename."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from skeleton.ai.training.rom_study import (
    BATCH_SCHEMA, RomStudyError, _canonical, _verify_existing_q_receipt,
)


def fixture(tmp_path):
    output = tmp_path / "receipt.json"
    grant = {
        "core_id": "gambatte", "target_id": "game_boy",
        "rights": {"review_id": "review-1", "rights_basis": "original:owned"},
    }
    lineage = {
        "rights_acknowledged": True, "source_sha256": "a" * 64,
        "rights_review_id": "review-1", "rights_basis": "original:owned",
        "approvals_manifest_sha256": "b" * 64,
        "core_id": "gambatte", "target_id": "game_boy",
    }
    doc = {
        "schema_version": BATCH_SCHEMA, "source_sha256": "a" * 64,
        "source_size_bytes": 32768,
        "core_id": "gambatte", "target_id": "game_boy",
        "approval_manifest_sha256": "b" * 64,
        "registry_digest": "c" * 64,
        "training_kind": "actual_replay_audited_tabular_q_policy",
        "neural_weights_updated": 0, "production_weights_modified": False,
        "model_promotion_authorized": False,
        "candidate_evidence": {
            "source_lineage": lineage,
            "policy_snapshot": {"snapshot_digest": "d" * 64},
            "actual_training_steps": 2,
            "actual_q_table_updates": 2,
            "actual_neural_parameter_updates": 0,
        },
    }
    return output, grant, doc


def check(path, grant):
    return _verify_existing_q_receipt(
        path, source_sha="a" * 64, size=32768,
        grant=grant, approvals_digest="b" * 64, registry_digest="c" * 64,
    )


def test_existing_receipt_requires_real_reverification(tmp_path, monkeypatch):
    path, grant, doc = fixture(tmp_path)
    path.write_bytes(_canonical(doc) + b"\n")
    from skeleton.jeeves import game_emulator_neural_world as neural
    verifier = Mock(return_value=([{}, {}], None, None, "e" * 64))
    monkeypatch.setattr(neural, "verify_neural_training_sources", verifier)
    assert len(check(path, grant)) == 64
    assert verifier.call_count == 1
    doc["candidate_evidence"]["actual_training_steps"] = 200
    path.write_bytes(_canonical(doc) + b"\n")
    with pytest.raises(RomStudyError, match="accounting"):
        check(path, grant)


def test_existing_name_cannot_bypass_source_rights_or_core(tmp_path, monkeypatch):
    path, grant, doc = fixture(tmp_path)
    from skeleton.jeeves import game_emulator_neural_world as neural
    forbidden = Mock(side_effect=AssertionError("should not validate forged source"))
    monkeypatch.setattr(neural, "verify_neural_training_sources", forbidden)
    for field, value in (("source_sha256", "9" * 64),
                         ("approval_manifest_sha256", "8" * 64),
                         ("core_id", "wrong")):
        bad = copy.deepcopy(doc)
        bad[field] = value
        path.write_bytes(_canonical(bad) + b"\n")
        with pytest.raises(RomStudyError, match="approved training identity"):
            check(path, grant)
    bad = copy.deepcopy(doc)
    bad["candidate_evidence"]["source_lineage"]["rights_review_id"] = "forged"
    path.write_bytes(_canonical(bad) + b"\n")
    with pytest.raises(RomStudyError, match="rights lineage"):
        check(path, grant)
    forbidden.assert_not_called()


def test_existing_receipt_rejects_noncanonical_or_symlinked_file(tmp_path):
    path, grant, doc = fixture(tmp_path)
    path.write_text(json.dumps(doc, indent=2))
    with pytest.raises(RomStudyError, match="approved training identity"):
        check(path, grant)
    path.unlink()
    true_file = tmp_path / "real.json"
    true_file.write_bytes(_canonical(doc) + b"\n")
    path.symlink_to(true_file)
    with pytest.raises(RomStudyError):
        check(path, grant)
