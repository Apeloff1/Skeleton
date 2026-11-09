"""ROM receipt reuse: actual tabular Q learner on deterministic simulated core.

The fixture executes real training and audited reverse-replay bookkeeping, but
is NOT a native console, licensed commercial ROM or production Jeeves model.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import pytest

from skeleton.ai.training.rom_study import (
    BATCH_SCHEMA, RomStudyError, _canonical, _verify_existing_q_receipt,
)
from skeleton.jeeves.game_emulator_training_lab import (
    EmulatorLabConfig, run_emulator_training_lab,
)
from skeleton.jeeves.game_learning_parallel import GameEnvironmentRequest
from skeleton.testing.test_game_emulator_training_lab import (
    ControlledNativeFixture, _request,
)


def trained_q_receipt(tmp_path: Path, runs: int = 1, approvals_digest: str = "b" * 64):
    """Make a genuine learned Q snapshot without a native libretro dependency."""
    source = sha256(b"original-homebrew-fixture").hexdigest()
    grant = {
        "core_id": "gambatte", "target_id": "game_boy",
        "rights": {"review_id": "review-1", "rights_basis": "original:owned"},
    }
    lineage = {
        "rights_acknowledged": True, "source_sha256": source,
        "rights_review_id": "review-1", "rights_basis": "original:owned",
        "approvals_manifest_sha256": approvals_digest,
        "core_id": "gambatte", "target_id": "game_boy",
    }
    with patch.object(
        GameEnvironmentRequest, "build",
        side_effect=lambda **_: ControlledNativeFixture(),
    ):
        evidence = run_emulator_training_lab(
            _request(), source_lineage=lineage,
            config=EmulatorLabConfig(
                max_runs=runs, steps_per_run=4, seed=42,
                heldout_episodes=1, stagnation_runs=10,
            ),
        )
    document = {
        "schema_version": BATCH_SCHEMA, "source_sha256": source,
        "source_size_bytes": 32768,
        "core_id": "gambatte", "target_id": "game_boy",
        "approval_manifest_sha256": approvals_digest,
        "registry_digest": "c" * 64,
        "training_kind": "actual_replay_audited_tabular_q_policy",
        "neural_weights_updated": 0, "production_weights_modified": False,
        "model_promotion_authorized": False,
        "candidate_evidence": evidence,
    }
    path = tmp_path / "receipt.json"
    path.write_bytes(_canonical(document) + b"\n")
    return path, grant, document, source


def verify(path, grant, source):
    return _verify_existing_q_receipt(
        path, source_sha=source, size=32768,
        grant=grant, approvals_digest="b" * 64,
        registry_digest="c" * 64,
    )


def test_short_one_episode_q_policy_is_reusable_without_neural_samples(tmp_path):
    path, grant, doc, source = trained_q_receipt(tmp_path, runs=1)
    assert doc["candidate_evidence"]["run_count"] == 1
    assert doc["candidate_evidence"]["neural_candidate_dataset"]["training_sample_count"] < 32
    assert len(verify(path, grant, source)) == 64


def test_source_rights_and_native_binding_mismatch_block_reuse(tmp_path):
    path, grant, doc, source = trained_q_receipt(tmp_path)
    for field, value in (
        ("source_sha256", "9" * 64),
        ("approval_manifest_sha256", "8" * 64),
        ("core_id", "wrong"),
    ):
        changed = dict(doc)
        changed[field] = value
        path.write_bytes(_canonical(changed) + b"\n")
        with pytest.raises(RomStudyError, match="approved training identity"):
            verify(path, grant, source)


def test_tampered_replay_receipt_and_policy_fail_closed(tmp_path):
    path, grant, doc, source = trained_q_receipt(tmp_path)
    replay = dict(doc)
    report = dict(doc["candidate_evidence"])
    audited = [dict(row) for row in report["audited_run_receipts"]]
    audited[0]["actual_steps"] -= 1
    report["audited_run_receipts"] = audited
    replay["candidate_evidence"] = report
    path.write_bytes(_canonical(replay) + b"\n")
    with pytest.raises(ValueError):
        verify(path, grant, source)
    path.write_bytes(_canonical(doc) + b"\n")
    assert len(verify(path, grant, source)) == 64


def test_symlinked_or_noncanonical_receipt_is_rejected(tmp_path):
    path, grant, doc, source = trained_q_receipt(tmp_path)
    path.write_text("  " + (_canonical(doc).decode("utf-8")) + "\n")
    with pytest.raises(RomStudyError, match="approved training identity"):
        verify(path, grant, source)
    path.unlink()
    real = tmp_path / "real.json"
    real.write_bytes(_canonical(doc) + b"\n")
    path.symlink_to(real)
    with pytest.raises(RomStudyError):
        verify(path, grant, source)
