"""Held-out incremental learning is separate from self-promotion and paper closure."""
from __future__ import annotations

import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from skeleton.ai.runtime.inference.artifact import write_local_model_artifact
from skeleton.app.local_ai import load_native_checkpoint
from skeleton.app.local_ai_improvement import (
    OfflineImprovementError,
    improve_local_model,
)
from skeleton.cortex.transformer import TinyTransformer
from tests.flgb.test_desktop_offline_ai import backend


class TestEvaluatedOfflineImprovement(unittest.TestCase):
    def _fixture(self, d: str) -> tuple[Path, Path, Path, Path]:
        root = Path(d)
        source = root / "base.json"
        train = root / "train.txt"
        heldout = root / "heldout.txt"
        dest = root / "candidate.json"
        write_local_model_artifact(backend(), source)
        train.write_text(
            ("user: hello assistant: world alpha\n" * 4),
            encoding="utf-8",
        )
        heldout.write_text("user: hello assistant: world beta\n", encoding="utf-8")
        return source, train, heldout, dest

    def test_verified_gradient_continuation_preserves_old_weights(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            source, train, heldout, dest = self._fixture(d)
            previous_bytes = source.read_bytes()
            previous = load_native_checkpoint(source)
            receipt = improve_local_model(source, train, heldout, dest, epochs=3)
            self.assertTrue(dest.exists())
            self.assertEqual(source.read_bytes(), previous_bytes)
            self.assertEqual(receipt.parent_model_digest, previous.model_digest)
            self.assertNotEqual(receipt.candidate_model_digest, previous.model_digest)
            self.assertEqual(receipt.tokenizer_digest, previous.tokenizer_digest)
            self.assertGreater(receipt.total_training_steps, 0)
            self.assertGreater(receipt.baseline_perplexity, receipt.accepted_perplexity)
            self.assertTrue(1 <= receipt.best_epoch <= receipt.attempted_epochs <= 4)
            new_model = load_native_checkpoint(dest)
            self.assertEqual(new_model.model_digest, receipt.candidate_model_digest)
            self.assertEqual(new_model.tokenizer_digest, previous.tokenizer_digest)
            self.assertFalse(receipt.to_dict()["independent_quality_certification"])
            self.assertTrue(receipt.to_dict()["rollback_checkpoint_retained"])

    def test_no_improvement_fails_closed_with_no_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            source, train, heldout, dest = self._fixture(d)
            original = source.read_bytes()
            with patch.object(TinyTransformer, "fit", return_value=0):
                with self.assertRaisesRegex(OfflineImprovementError, "no held-out improvement"):
                    improve_local_model(source, train, heldout, dest, epochs=2)
            self.assertFalse(dest.exists())
            self.assertEqual(source.read_bytes(), original)

    def test_rejects_validation_leakage_before_gradient_steps(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            source, train, heldout, dest = self._fixture(d)
            heldout.write_text(train.read_text(encoding="utf-8"), encoding="utf-8")
            with patch.object(TinyTransformer, "fit", side_effect=AssertionError("must not train")):
                with self.assertRaisesRegex(OfflineImprovementError, "identical"):
                    improve_local_model(source, train, heldout, dest)
            self.assertFalse(dest.exists())
            heldout.write_text("user: hello assistant: world alpha\n", encoding="utf-8")
            with patch.object(TinyTransformer, "fit", side_effect=AssertionError("must not train")):
                with self.assertRaisesRegex(OfflineImprovementError, "overlaps"):
                    improve_local_model(source, train, heldout, dest)
            self.assertFalse(dest.exists())

    def test_rejects_wrong_vocabulary_and_missing_evaluation(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            source, train, heldout, dest = self._fixture(d)
            heldout.write_text("unknown new words unavailable\n", encoding="utf-8")
            with self.assertRaisesRegex(OfflineImprovementError, "missing"):
                improve_local_model(source, train, heldout, dest)
            with self.assertRaisesRegex(OfflineImprovementError, "separate"):
                improve_local_model(source, train, train, dest)
            self.assertFalse(dest.exists())

    def test_refuses_overwrite_and_invalid_budget(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            source, train, heldout, dest = self._fixture(d)
            dest.write_text("keep", encoding="utf-8")
            for epochs in (0, 5, True):
                with self.assertRaises(OfflineImprovementError):
                    improve_local_model(source, train, heldout, dest, epochs=epochs)
            with self.assertRaisesRegex(OfflineImprovementError, "already exist"):
                improve_local_model(source, train, heldout, dest, epochs=1)
            self.assertEqual(dest.read_text(encoding="utf-8"), "keep")

    def test_cli_improvement_contract_and_receipt(self) -> None:
        from skeleton.app.cli import run_app_cli

        with tempfile.TemporaryDirectory() as d:
            source, train, heldout, dest = self._fixture(d)
            output = StringIO()
            with redirect_stdout(output):
                code = run_app_cli([
                    "local-ai", "--improve-model", str(source),
                    "--train-corpus", str(train),
                    "--eval-corpus", str(heldout),
                    "--output-model", str(dest),
                    "--epochs", "3", "--json",
                ])
            self.assertEqual(code, 0, output.getvalue())
            report = json.loads(output.getvalue())
            self.assertLess(report["accepted_perplexity"], report["baseline_perplexity"])
            self.assertEqual(load_native_checkpoint(dest).model_digest, report["candidate_model_digest"])

    def test_cli_cannot_skip_independent_evaluation(self) -> None:
        from skeleton.app.cli import run_app_cli

        for params in (
            ["--improve-model", "base.json", "--train-corpus", "data.txt", "--output-model", "out.json"],
            ["--eval-corpus", "validation.txt"],
            ["--improve-model", "base.json", "--train-corpus", "data.txt", "--eval-corpus", "eval.txt"],
        ):
            out = StringIO()
            with redirect_stdout(out):
                code = run_app_cli(["local-ai", *params])
            self.assertEqual(code, 2, out.getvalue())


if __name__ == "__main__":
    unittest.main()
