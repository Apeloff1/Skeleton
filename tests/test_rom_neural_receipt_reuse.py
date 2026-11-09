"""Saved neural ROM shadow candidates must be reverified before reuse.

The fake model below is a test double, not trained neural parameters or a
native-emulator compatibility claim. Production validation remains canonical.
"""
from __future__ import annotations

import copy
from unittest.mock import Mock

import pytest

from skeleton.ai.training.rom_study import (
    RomStudyError, _canonical, _verify_existing_neural_candidate,
)
from skeleton.jeeves.game_learning import _digest


SOURCE = "a" * 64
Q = "b" * 64
REPORT = "c" * 64
POLICY = "d" * 64
MODEL = "e" * 64


def candidate(tmp_path):
    model = {
        "model_digest": MODEL,
        "source_evidence_digest": REPORT,
        "source_policy_snapshot_digest": POLICY,
        "real_optimizer_steps": 3,
        "measured_predictive_gate": "candidate_predictive_gain_measured",
    }
    heldout = {
        "world_model_digest": MODEL,
        "parent_emulator_evidence_digest": REPORT,
        "real_neural_optimizer_steps": 3,
        "candidate_status": "candidate_predictive_gain_measured",
        "production_model_promotion": False,
    }
    heldout["report_digest"] = _digest(heldout)
    document = {
        "schema_version": "skeleton.jeeves.rom_neural_candidate.v1",
        "rom_sha256": SOURCE,
        "source_q_receipt_sha256": Q,
        "source_emulator_report_digest": REPORT,
        "model": model, "heldout_measurements": heldout,
        "production_jeeves_weights_updated": False,
        "candidate_only_no_auto_promotion": True,
    }
    path = tmp_path / "saved-world.json"
    path.write_bytes(_canonical(document) + b"\n")
    return path, document


def verify(path):
    return _verify_existing_neural_candidate(
        path, source_sha=SOURCE, q_digest=Q,
        source_report_digest=REPORT, policy_digest=POLICY,
    )


def test_verified_candidate_reuse_preserves_read_only_model_custody(tmp_path, monkeypatch):
    from skeleton.jeeves import game_emulator_neural_world as neural
    validator = Mock(return_value=MODEL)
    monkeypatch.setattr(neural, "validate_neural_world_checkpoint", validator)
    path, document = candidate(tmp_path)
    result = verify(path)
    assert result["state"] == "previous_neural_candidate_verified_not_retrained"
    assert result["model_digest"] == MODEL
    assert result["neural_training_reexecuted"] is False
    assert result["production_weights_modified"] is False
    validator.assert_called_once_with(document["model"])


def test_candidate_source_drift_cannot_reuse_saved_file(tmp_path, monkeypatch):
    from skeleton.jeeves import game_emulator_neural_world as neural
    validator = Mock(return_value=MODEL)
    monkeypatch.setattr(neural, "validate_neural_world_checkpoint", validator)
    path, doc = candidate(tmp_path)
    for key, value in (
        ("rom_sha256", "f" * 64),
        ("source_q_receipt_sha256", "f" * 64),
        ("source_emulator_report_digest", "f" * 64),
        ("production_jeeves_weights_updated", True),
    ):
        changed = dict(doc)
        changed[key] = value
        path.write_bytes(_canonical(changed) + b"\n")
        with pytest.raises(RomStudyError):
            verify(path)
    validator.assert_not_called()


def test_forged_optimizer_or_heldout_result_cannot_be_reused(tmp_path, monkeypatch):
    from skeleton.jeeves import game_emulator_neural_world as neural
    monkeypatch.setattr(
        neural, "validate_neural_world_checkpoint",
        Mock(return_value=MODEL),
    )
    path, doc = candidate(tmp_path)
    bad = copy.deepcopy(doc)
    bad["heldout_measurements"]["real_neural_optimizer_steps"] = 0
    bad["heldout_measurements"]["report_digest"] = _digest({
        k: v for k, v in bad["heldout_measurements"].items() if k != "report_digest"
    })
    path.write_bytes(_canonical(bad) + b"\n")
    with pytest.raises(RomStudyError, match="ancestry"):
        verify(path)
    bad = copy.deepcopy(doc)
    bad["heldout_measurements"]["candidate_status"] = "unmeasured-success"
    path.write_bytes(_canonical(bad) + b"\n")
    with pytest.raises(RomStudyError):
        verify(path)
