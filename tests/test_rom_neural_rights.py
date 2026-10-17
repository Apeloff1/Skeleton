"""Fresh rights approval is mandatory for standalone ROM shadow optimization."""
from __future__ import annotations

import json
from unittest.mock import Mock, patch

import pytest

from skeleton.ai.training.rom_study import (
    APPROVAL_SCHEMA, RomStudyError, _load_approvals, train_neural_candidate,
)
from tests.test_rom_receipt_reuse import trained_q_receipt


def _source_and_approval(tmp_path):
    path = tmp_path / "approval.json"
    source = "placeholder"
    # The source digest is assigned after the actual fixture is established.
    from hashlib import sha256
    source = sha256(b"original-homebrew-fixture").hexdigest()
    grant = {
        "sha256": source, "content_size_bytes": 32768,
        "target_id": "game_boy", "core_id": "gambatte",
        "rights": {
            "rights_holder": "Homebrew Fixture Author",
            "rights_basis": "original:owned",
            "review_id": "review-1",
            "training_permitted": True, "human_reviewed": True,
        },
    }
    path.write_text(json.dumps({"schema_version": APPROVAL_SCHEMA, "roms": [grant]}))
    digest = _load_approvals(path)[1]
    receipt, _, _, _ = trained_q_receipt(tmp_path, runs=1, approvals_digest=digest)
    return receipt, path, grant


def _forbidden_optimizer():
    from skeleton.jeeves import game_emulator_neural_world as neural
    blocked = Mock(side_effect=AssertionError("shadow optimizer must not run"))
    return patch.object(neural, "train_neural_world_from_evidence", blocked), blocked


def test_missing_current_approval_blocks_standalone_neural_training(tmp_path):
    receipt, approval, _ = _source_and_approval(tmp_path)
    pair, blocked = _forbidden_optimizer()
    with pair:
        with pytest.raises(RomStudyError):
            train_neural_candidate(
                receipt, tmp_path, approvals_path=tmp_path / "does-not-exist.json",
            )
    blocked.assert_not_called()


def test_rights_revocation_blocks_optimizer_despite_existing_q_receipt(tmp_path):
    receipt, approval, grant = _source_and_approval(tmp_path)
    grant["rights"]["training_permitted"] = False
    approval.write_text(json.dumps({"schema_version": APPROVAL_SCHEMA, "roms": [grant]}))
    pair, blocked = _forbidden_optimizer()
    with pair:
        with pytest.raises(RomStudyError, match="unapproved"):
            train_neural_candidate(receipt, tmp_path, approvals_path=approval)
    blocked.assert_not_called()


def test_reapproval_revision_invalidates_prior_q_receipt(tmp_path):
    receipt, approval, grant = _source_and_approval(tmp_path)
    grant["rights"]["review_id"] = "new-human-review-002"
    approval.write_text(json.dumps({"schema_version": APPROVAL_SCHEMA, "roms": [grant]}))
    pair, blocked = _forbidden_optimizer()
    with pair:
        with pytest.raises(RomStudyError, match="current source rights"):
            train_neural_candidate(receipt, tmp_path, approvals_path=approval)
    blocked.assert_not_called()


def test_current_approval_accepts_q_then_applies_independent_neural_threshold(tmp_path):
    receipt, approval, _ = _source_and_approval(tmp_path)
    pair, blocked = _forbidden_optimizer()
    with pair:
        # One genuine episode has only four replay-verified samples, so it is
        # valid Q learning but NOT yet admitted for 32+ sample neural training.
        with pytest.raises(ValueError, match="at least three|insufficient"):
            train_neural_candidate(receipt, tmp_path, approvals_path=approval)
    blocked.assert_not_called()
