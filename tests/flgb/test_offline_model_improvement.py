"""Held-out incremental learning is separate from self-promotion and paper closure."""
from __future__ import annotations

import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from skeleton.ai.model_runtime import NativeLLMRuntime
from skeleton.ai.runtime.inference.artifact import write_local_model_artifact
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
from skeleton.app.local_ai import load_native_checkpoint
from skeleton.app.local_ai_improvement import (
    OfflineImprovementError,
    compare_local_models,
    improve_local_model,
)
from skeleton.cortex.transformer import TinyTransformer


class TestEvaluatedOfflineImprovement(unittest.TestCase):
    def _fixture(self, d: str) -> tuple[Path, Path, Path, Path]:
        root = Path(d)
        source = root / "base.json"
        train = root / "train.txt"
        heldout = root / "heldout.txt"
        dest = root / "candidate.json"
        # Use the same normalized role vocabulary admitted by the real
        # CPU corpus trainer. `user:` tokenizes to `user`, not `user:`.
        native = TinyTransformer(
            vocab=("user", "assistant", "hello", "world", "alpha", "beta"),
            dim=8, ctx=96, seed=37, n_heads=2, n_layers=2, d_ff=16,
        )
        write_local_model_artifact(NativeRuntimeLocalModel(NativeLLMRuntime(native)), source)
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

    def test_heldout_comparison_reports_actual_verified_model_gain(self) -> None:
        from skeleton.app.cli import run_app_cli

        with tempfile.TemporaryDirectory() as d:
            source, train, heldout, dest = self._fixture(d)
            receipt = improve_local_model(source, train, heldout, dest, epochs=3)
            comparison = compare_local_models(source, dest, heldout)
            self.assertTrue(comparison.improves)
            self.assertEqual(comparison.baseline_model_digest, receipt.parent_model_digest)
            self.assertEqual(comparison.candidate_model_digest, receipt.candidate_model_digest)
            self.assertEqual(comparison.validation_source_sha256, receipt.validation_source_sha256)
            self.assertEqual(comparison.tokenizer_digest, receipt.tokenizer_digest)
            self.assertFalse(comparison.to_dict()["candidate_promoted"])
            self.assertAlmostEqual(comparison.baseline_perplexity, receipt.baseline_perplexity)
            self.assertAlmostEqual(comparison.candidate_perplexity, receipt.accepted_perplexity)
            output = StringIO()
            with redirect_stdout(output):
                code = run_app_cli([
                    "local-ai", "--compare-model", str(source),
                    "--candidate-model", str(dest),
                    "--eval-corpus", str(heldout), "--json",
                ])
            self.assertEqual(code, 0, output.getvalue())
            self.assertTrue(json.loads(output.getvalue())["improves"])

    def test_comparison_rejects_identical_checkpoint_and_bad_vocabulary(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            source, train, heldout, dest = self._fixture(d)
            with self.assertRaisesRegex(OfflineImprovementError, "distinct"):
                compare_local_models(source, source, heldout)
            heldout.write_text("outofvocabulary words unknown\n", encoding="utf-8")
            native = TinyTransformer(
                vocab=("user", "assistant", "hello", "world", "alpha", "beta"),
                dim=8, ctx=96, seed=47, n_heads=2, n_layers=2, d_ff=16,
            )
            write_local_model_artifact(
                NativeRuntimeLocalModel(NativeLLMRuntime(native)), dest,
            )
            with self.assertRaisesRegex(OfflineImprovementError, "missing"):
                compare_local_models(source, dest, heldout)

    def test_cli_comparison_rejects_missing_candidate_and_reports_regression(self) -> None:
        from skeleton.app.cli import run_app_cli

        with tempfile.TemporaryDirectory() as d:
            source, train, heldout, dest = self._fixture(d)
            out = StringIO()
            with redirect_stdout(out):
                self.assertEqual(run_app_cli([
                    "local-ai", "--compare-model", str(source),
                    "--eval-corpus", str(heldout),
                ]), 2)
            native = TinyTransformer(
                vocab=("user", "assistant", "hello", "world", "alpha", "beta"),
                dim=8, ctx=96, seed=47, n_heads=2, n_layers=2, d_ff=16,
            )
            write_local_model_artifact(
                NativeRuntimeLocalModel(NativeLLMRuntime(native)), dest,
            )
            with patch.object(TinyTransformer, "perplexity", side_effect=[2.0, 3.0]):
                with redirect_stdout(out := StringIO()):
                    code = run_app_cli([
                        "local-ai", "--compare-model", str(source),
                        "--candidate-model", str(dest),
                        "--eval-corpus", str(heldout), "--json",
                    ])
            self.assertEqual(code, 1)
            self.assertFalse(json.loads(out.getvalue())["improves"])

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
