"""Candidate-only recovery: post-SGD review crash must not retrain or promote."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from skeleton.ai.training.jeeves_production_game_recovery import finalize
from skeleton.ai.training.jeeves_production_game_train import (
    ProductionCheckpointError, SCHEMA as TRAIN_SCHEMA,
)
from skeleton.ai.training.jeeves_production_game_session import SCHEMA as SESSION_SCHEMA


class FinishedCandidateRecoveryTests(unittest.TestCase):
    def _files(self, directory: Path) -> dict:
        operator = directory / "operator"
        model_dir = directory / "serving"
        dataset_dir = directory / "datasets"
        operator.mkdir()
        model_dir.mkdir()
        dataset_dir.mkdir()
        model = model_dir / "production-state.json"
        model.write_text(json.dumps({"protected_parent_data": "p" * 150}))
        baseline = model.read_bytes()
        expected_hash = sha256(baseline).hexdigest()
        backup = operator / "game-001-parent-backup.json"
        backup.write_bytes(baseline)
        candidate = operator / "game-001-candidate.json"
        candidate.write_text(json.dumps({
            "own": {}, "lms": {}, "transformer": {"claimed_steps": 7},
            "candidate_bytes": "c" * 80,
        }))
        candidate_sha = sha256(candidate.read_bytes()).hexdigest()
        corpus = {
            "manifest_sha256": "a" * 64,
            "train_sha256": "b" * 64,
            "heldout_sha256": "c" * 64,
            "rights_review_id": "fixture-approved-review",
            "train_examples": 64,
            "heldout_examples": 16,
        }
        training = operator / "game-001-training.json"
        training.write_text(json.dumps({
            "schema_version": TRAIN_SCHEMA,
            "source_checkpoint_sha256": expected_hash,
            "candidate_sha256": candidate_sha,
            "status": "candidate_trained_needs_game_design_review",
            "production_weights_modified": False,
            "candidate_promoted": False,
            "training_steps_before": 2,
            "training_steps_after": 12,
            "built_in_smoke_curriculum_only": False,
            "dataset_receipt": corpus,
        }))
        manifest = dataset_dir / "approved.json"
        manifest.write_text("{}")
        return {
            "directory": operator, "parent": model, "manifest": manifest,
            "parent_sha": expected_hash, "candidate_sha": candidate_sha,
            "corpus": corpus,
        }

    def _finalize(self, context):
        return finalize(
            run_id="game-001", attestation=context["directory"] / "attestation.json",
            output_directory=context["directory"],
            dataset_manifest=context["manifest"],
        )

    def test_valid_training_receipt_can_be_finalized_without_sgd(self):
        with tempfile.TemporaryDirectory() as root:
            files = self._files(Path(root))
            review = {
                "schema_version": "skeleton.jeeves.game_design_answer_benchmark.v1",
                "parent_checkpoint_sha256": files["parent_sha"],
                "candidate_checkpoint_sha256": files["candidate_sha"],
                "results": [{"prompt": str(i)} for i in range(24)],
            }
            with patch(
                "skeleton.ai.training.jeeves_production_game_recovery.inspect",
                return_value={
                    "status": "ready_for_operator_training",
                    "checkpoint_path": str(files["parent"]),
                    "checkpoint_sha256": files["parent_sha"],
                },
            ), patch(
                "skeleton.ai.training.jeeves_production_game_recovery.load_approved_corpus",
                return_value=((), {}, files["corpus"]),
            ), patch(
                "skeleton.ai.training.jeeves_production_game_recovery.compare",
                return_value=review,
            ):
                result = self._finalize(files)
            self.assertEqual(result["status"], "candidate_trained_requires_independent_review")
            self.assertTrue(result["recovered_after_interruption"])
            self.assertFalse(result["candidate_promoted"])
            self.assertFalse(result["production_weights_modified"])
            saved = files["directory"] / "game-001-manifest.json"
            self.assertTrue(saved.exists())
            self.assertEqual(json.loads(saved.read_text())["candidate_sha256"],
                             files["candidate_sha"])
            self.assertTrue((files["directory"] / "game-001-game-review.json").exists())
            self.assertEqual(sha256(files["parent"].read_bytes()).hexdigest(),
                             files["parent_sha"])

    def test_finalizer_never_overwrites_preexisting_manifest(self):
        with tempfile.TemporaryDirectory() as root:
            files = self._files(Path(root))
            terminal = files["directory"] / "game-001-manifest.json"
            terminal.write_text("existing manifest")
            with self.assertRaisesRegex(ProductionCheckpointError, "already been finalized"):
                self._finalize(files)
            self.assertEqual(terminal.read_text(), "existing manifest")

    def test_tampered_candidate_sha_cannot_be_finalized(self):
        with tempfile.TemporaryDirectory() as root:
            files = self._files(Path(root))
            candidate = files["directory"] / "game-001-candidate.json"
            candidate.write_bytes(candidate.read_bytes() + b" ")
            with patch(
                "skeleton.ai.training.jeeves_production_game_recovery.inspect",
                return_value={
                    "status": "ready_for_operator_training",
                    "checkpoint_path": str(files["parent"]),
                    "checkpoint_sha256": files["parent_sha"],
                },
            ):
                with self.assertRaisesRegex(ProductionCheckpointError, "lineage"):
                    self._finalize(files)

    def test_untrusted_runtime_claim_does_not_allow_recovery(self):
        with tempfile.TemporaryDirectory() as root:
            files = self._files(Path(root))
            with patch(
                "skeleton.ai.training.jeeves_production_game_recovery.inspect",
                return_value={"status": "blocked", "blockers": ["unverified_runtime"]},
            ):
                with self.assertRaisesRegex(ProductionCheckpointError, "admission blocked"):
                    self._finalize(files)

    def test_mismatched_review_fails_without_replacement(self):
        with tempfile.TemporaryDirectory() as root:
            files = self._files(Path(root))
            stale = files["directory"] / "game-001-game-review.json"
            stale.write_text(json.dumps({"unverified": "reply", "filler": "x" * 70}))
            with patch(
                "skeleton.ai.training.jeeves_production_game_recovery.inspect",
                return_value={
                    "status": "ready_for_operator_training",
                    "checkpoint_path": str(files["parent"]),
                    "checkpoint_sha256": files["parent_sha"],
                },
            ), patch(
                "skeleton.ai.training.jeeves_production_game_recovery.load_approved_corpus",
                return_value=((), {}, files["corpus"]),
            ), patch(
                "skeleton.ai.training.jeeves_production_game_recovery.compare",
                return_value={"results": [{"prompt": str(i)} for i in range(24)]},
            ):
                with self.assertRaisesRegex(ProductionCheckpointError, "inconsistent"):
                    self._finalize(files)
            self.assertIn("unverified", stale.read_text())
            self.assertFalse((files["directory"] / "game-001-manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
