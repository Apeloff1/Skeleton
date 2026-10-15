"""Offline custody contracts for resumable production-derived Jeeves SGD."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from skeleton.ai.training.jeeves_production_game_train import ProductionCheckpointError
from skeleton.ai.training.jeeves_training_progress import CandidateProgress


class ImmutableCandidateProgressTests(unittest.TestCase):
    def _progress(self, location: Path, *, config: str = "b" * 64,
                  parent: str = "a" * 64) -> CandidateProgress:
        return CandidateProgress(
            directory=location, run_id="game-001",
            parent_sha256=parent, config_digest=config,
            total_batches=3, parent_steps=0, selected_model_key="transformer",
        )

    def _model(self):
        from skeleton.cortex.transformer import TinyTransformer
        return TinyTransformer(vocab=["one", "two"], dim=8, ctx=6, seed=12)

    def test_new_run_stage_zero_and_resumable_cursor(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            progress = self._progress(root)
            self.assertIsNone(progress.latest(resume=False))
            model = self._model()
            initial = model.snapshot()
            initial_receipt = progress.write(0, initial)
            self.assertEqual(initial_receipt["completed_updates"], 0)
            model.fit(("one two one",), lr=0.004)
            one = progress.write(1, model.snapshot())
            self.assertGreater(one["completed_updates"], 0)
            self.assertEqual(progress.initial_snapshot(), initial)
            index, resumed = progress.latest(resume=True)
            self.assertEqual(index, 1)
            self.assertEqual(resumed["receipt"], one)
            self.assertEqual(resumed["snapshot"], model.snapshot())
            with self.assertRaisesRegex(ProductionCheckpointError, "already has"):
                progress.latest(resume=False)

    def test_progress_model_lineage_cannot_change(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._progress(root).write(0, self._model().snapshot())
            with self.assertRaisesRegex(ProductionCheckpointError, "another model"):
                self._progress(root, parent="c" * 64).latest(resume=True)
            with self.assertRaisesRegex(ProductionCheckpointError, "another model"):
                self._progress(root, config="d" * 64).latest(resume=True)

    def test_resume_refuses_missing_or_changed_weights(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            progress = self._progress(root)
            with self.assertRaisesRegex(ProductionCheckpointError, "no committed"):
                progress.latest(resume=True)
            progress.write(0, self._model().snapshot())
            weights, _ = progress._paths(0)
            weights.write_bytes(weights.read_bytes() + b"\n")
            with self.assertRaisesRegex(ProductionCheckpointError, "weights have changed"):
                progress.latest(resume=True)

    def test_optimizer_cursor_must_advance(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            progress = self._progress(root)
            snapshot = self._model().snapshot()
            progress.write(0, snapshot)
            with self.assertRaisesRegex(ProductionCheckpointError, "did not advance"):
                progress.write(1, snapshot)

    def test_no_implicit_reuse_or_skipped_cursor(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            progress = self._progress(root)
            model = self._model()
            progress.write(0, model.snapshot())
            model.fit(("one two one",), lr=0.004)
            with self.assertRaisesRegex(ProductionCheckpointError, "committed training cursor"):
                progress.write(2, model.snapshot())


if __name__ == "__main__":
    unittest.main()
