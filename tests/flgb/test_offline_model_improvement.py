"""Held-out incremental learning is separate from self-promotion and paper closure."""
from __future__ import annotations

import json
import math
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
from skeleton.app.local_ai_training import OfflineTrainingError, publish_native_checkpoint_no_replace
from skeleton.app.local_ai_improvement import (
    OfflineImprovementError,
    compare_local_models,
    improve_local_model,
    _token_weighted_perplexity,
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

    def test_rejects_tokenizer_equivalent_leakage_without_training(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            source, train, heldout, dest = self._fixture(d)
            # Case and punctuation changes still normalize to the same IDs.
            heldout.write_text(
                "USER hello ASSISTANT world alpha\n", encoding="utf-8",
            )
            with patch.object(
                TinyTransformer, "fit",
                side_effect=AssertionError("leaked validation must not train"),
            ):
                with self.assertRaisesRegex(OfflineImprovementError, "normalized"):
                    improve_local_model(source, train, heldout, dest)
            self.assertFalse(dest.exists())

    def test_rejects_embedded_heldout_passage_before_any_gradient(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source, train, heldout, destination = self._fixture(directory)
            # Not an identical line: the evaluation passage was copied from
            # inside a longer training example after token normalization.
            train.write_text(
                "user hello assistant world alpha beta\n",
                encoding="utf-8",
            )
            heldout.write_text(
                "HELLO, assistant world alpha\n",
                encoding="utf-8",
            )
            with patch.object(
                TinyTransformer, "fit",
                side_effect=AssertionError("leaked holdout must not train"),
            ):
                with self.assertRaisesRegex(OfflineImprovementError, "overlaps"):
                    improve_local_model(source, train, heldout, destination)
            self.assertFalse(destination.exists())

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
            heldout.write_text("outofvocabulary words unknown tokens\n", encoding="utf-8")
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
            with patch.object(
                TinyTransformer, "logprob",
                side_effect=[-math.log(2.0), -math.log(3.0)],
            ):
                with redirect_stdout(out := StringIO()):
                    code = run_app_cli([
                        "local-ai", "--compare-model", str(source),
                        "--candidate-model", str(dest),
                        "--eval-corpus", str(heldout), "--json",
                    ])
            self.assertEqual(code, 1)
            self.assertFalse(json.loads(out.getvalue())["improves"])

    def test_concurrent_checkpoint_writer_never_overwrites_foreign_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source, train, heldout, dest = self._fixture(directory)
            model = load_native_checkpoint(source)
            previous = source.read_bytes()

            def concurrent_writer(_staged, target):
                Path(target).write_text("rival checkpoint", encoding="utf-8")
                raise FileExistsError("another writer claimed the filename")

            with patch("os.link", side_effect=concurrent_writer):
                with self.assertRaisesRegex(OfflineTrainingError, "already exists"):
                    publish_native_checkpoint_no_replace(model, dest)
            self.assertEqual(dest.read_text(encoding="utf-8"), "rival checkpoint")
            self.assertEqual(source.read_bytes(), previous)
            self.assertEqual(list(Path(directory).glob(".skeleton-native-stage-*")), [])

    def test_atomic_checkpoint_publication_keeps_canonical_model_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source, _, _, dest = self._fixture(directory)
            model = load_native_checkpoint(source)
            receipt = publish_native_checkpoint_no_replace(model, dest)
            restored = load_native_checkpoint(dest)
            self.assertEqual(receipt.model_digest, restored.model_digest)
            self.assertEqual(restored.model_digest, model.model_digest)
            self.assertEqual(list(Path(directory).glob(".skeleton-native-stage-*")), [])

    def test_heldout_perplexity_weights_prediction_tokens_not_lines(self) -> None:
        model = TinyTransformer(
            vocab=("hello", "world", "alpha", "beta"),
            dim=8, ctx=32, seed=31, n_heads=2, n_layers=1, d_ff=16,
        )
        short = "hello world alpha"
        long = "hello world alpha beta world"
        short_count = len(model._ids(short)) - 1
        long_count = len(model._ids(long)) - 1
        self.assertNotEqual(short_count, long_count)
        with patch.object(
            TinyTransformer, "logprob",
            side_effect=[-math.log(2.0), -math.log(4.0)],
        ):
            measured = _token_weighted_perplexity(model, [short, long])
        expected = math.exp(
            (short_count * math.log(2.0) + long_count * math.log(4.0))
            / (short_count + long_count)
        )
        self.assertAlmostEqual(measured, expected)
        # Taking an unweighted mean of line scores is not equivalent.
        self.assertNotAlmostEqual(measured, math.sqrt(2.0 * 4.0))

    def test_protected_suite_rejects_training_overlap_before_gradient(self) -> None:
        from skeleton.app.local_ai_benchmark import SCHEMA

        with tempfile.TemporaryDirectory() as directory:
            source, train, heldout, dest = self._fixture(directory)
            suite = Path(directory) / "protected.json"
            suite.write_text(json.dumps({
                "schema": SCHEMA,
                "cases": [
                    {"id": "overlap", "category": "safety",
                     "text": "user hello assistant world alpha"},
                ],
            }), encoding="utf-8")
            parent = source.read_bytes()
            with patch.object(
                TinyTransformer, "fit", side_effect=AssertionError("leaked case must not train"),
            ):
                with self.assertRaisesRegex(OfflineImprovementError, "overlaps"):
                    improve_local_model(
                        source, train, heldout, dest, protected_suite=suite,
                    )
            self.assertFalse(dest.exists())
            self.assertEqual(source.read_bytes(), parent)

    def test_protected_suite_must_pass_before_new_weights_are_published(self) -> None:
        from skeleton.app.local_ai_benchmark import SCHEMA

        with tempfile.TemporaryDirectory() as directory:
            source, train, heldout, dest = self._fixture(directory)
            suite = Path(directory) / "protected.json"
            suite.write_text(json.dumps({
                "schema": SCHEMA,
                "cases": [
                    {"id": "a", "category": "safety", "text": "alpha beta user"},
                    {"id": "b", "category": "safety", "text": "beta alpha user"},
                    {"id": "c", "category": "dialog", "text": "assistant beta alpha"},
                    {"id": "d", "category": "dialog", "text": "alpha assistant beta"},
                ],
            }), encoding="utf-8")
            original = source.read_bytes()
            with patch(
                "skeleton.app.local_ai_improvement._token_weighted_perplexity",
                side_effect=[4.0, 3.0, 3.0],
            ), patch(
                "skeleton.app.local_ai_benchmark.compare_benchmark_results",
                return_value={"passes_local_regression_gate": False},
            ):
                with self.assertRaisesRegex(OfflineImprovementError, "protected benchmark"):
                    improve_local_model(
                        source, train, heldout, dest, protected_suite=suite,
                    )
            self.assertFalse(dest.exists())
            self.assertEqual(source.read_bytes(), original)
            with patch(
                "skeleton.app.local_ai_improvement._token_weighted_perplexity",
                side_effect=[4.0, 3.0, 3.0],
            ), patch(
                "skeleton.app.local_ai_benchmark.compare_benchmark_results",
                return_value={"passes_local_regression_gate": True},
            ):
                receipt = improve_local_model(
                    source, train, heldout, dest, protected_suite=suite,
                )
            self.assertTrue(dest.is_file())
            self.assertTrue(receipt.protected_suite_passed)
            self.assertEqual(receipt.protected_suite_cases, 4)
            self.assertEqual(len(receipt.protected_suite_digest), 64)
            self.assertEqual(source.read_bytes(), original)

    def test_cli_protected_suite_requires_improvement_command(self) -> None:
        from skeleton.app.cli import run_app_cli

        with redirect_stdout(StringIO()):
            self.assertEqual(run_app_cli([
                "local-ai", "--protect-suite", "bench.json",
            ]), 2)

    def test_changed_training_data_after_sgd_prevents_publication(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            source, train, heldout, dest = self._fixture(d)
            parent = source.read_bytes()
            real_fit = TinyTransformer.fit

            def fit_and_edit_text(model, texts, **kwargs):
                steps = real_fit(model, texts, **kwargs)
                train.write_text(
                    "user hello assistant beta alpha\n", encoding="utf-8",
                )
                return steps

            with patch.object(TinyTransformer, "fit", new=fit_and_edit_text):
                with patch(
                    "skeleton.app.local_ai_improvement._token_weighted_perplexity",
                    side_effect=[4.0, 3.0, 3.0],
                ):
                    with self.assertRaisesRegex(
                        OfflineImprovementError, "source changed",
                    ):
                        improve_local_model(source, train, heldout, dest)
            self.assertFalse(dest.exists())
            self.assertEqual(source.read_bytes(), parent)

    def test_changed_parent_checkpoint_during_sgd_blocks_new_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            source, train, heldout, dest = self._fixture(d)
            real_fit = TinyTransformer.fit

            def fit_and_change_source_artifact(model, texts, **kwargs):
                steps = real_fit(model, texts, **kwargs)
                with source.open("ab") as stream:
                    stream.write(b"\n")
                return steps

            with patch.object(TinyTransformer, "fit", new=fit_and_change_source_artifact):
                with patch(
                    "skeleton.app.local_ai_improvement._token_weighted_perplexity",
                    side_effect=[4.0, 3.0, 3.0],
                ):
                    with self.assertRaisesRegex(
                        OfflineImprovementError, "checkpoint changed",
                    ):
                        improve_local_model(source, train, heldout, dest)
            self.assertFalse(dest.exists())

    def test_changed_heldout_data_during_sgd_prevents_publication(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            source, train, heldout, dest = self._fixture(d)
            real_fit = TinyTransformer.fit

            def fit_and_edit_heldout(model, texts, **kwargs):
                steps = real_fit(model, texts, **kwargs)
                heldout.write_text(
                    "user hello assistant world alpha beta\n", encoding="utf-8",
                )
                return steps

            with patch.object(TinyTransformer, "fit", new=fit_and_edit_heldout):
                with patch(
                    "skeleton.app.local_ai_improvement._token_weighted_perplexity",
                    side_effect=[4.0, 3.0, 3.0],
                ):
                    with self.assertRaisesRegex(
                        OfflineImprovementError, "source changed",
                    ):
                        improve_local_model(source, train, heldout, dest)
            self.assertFalse(dest.exists())

    def test_training_uses_isolated_clone_and_never_mutates_baseline_runtime(self) -> None:
        from skeleton.app.local_ai_benchmark import SCHEMA
        from skeleton.ai.runtime.inference.artifact import (
            load_local_model_artifact as actual_loader,
        )

        with tempfile.TemporaryDirectory() as directory:
            source, train, heldout, dest = self._fixture(directory)
            suite = Path(directory) / "guarded.json"
            suite.write_text(json.dumps({
                "schema": SCHEMA,
                "cases": [
                    {"id": "one", "category": "safety", "text": "alpha beta user"},
                    {"id": "two", "category": "safety", "text": "beta alpha user"},
                    {"id": "three", "category": "dialog", "text": "assistant beta alpha"},
                    {"id": "four", "category": "dialog", "text": "alpha assistant beta"},
                ],
            }), encoding="utf-8")
            retained = []
            original_fit = TinyTransformer.fit

            def load_with_baseline_tracking(path):
                loaded = actual_loader(path)
                if not retained:
                    retained.append(loaded.model)
                return loaded

            def assert_model_is_clone(model, texts, **kwargs):
                self.assertTrue(retained)
                self.assertIsNot(model, retained[0].runtime.model)
                retained[0].assert_identity()
                steps = original_fit(model, texts, **kwargs)
                retained[0].assert_identity()
                return steps

            with patch(
                "skeleton.app.local_ai_improvement.load_local_model_artifact",
                side_effect=load_with_baseline_tracking,
            ), patch.object(
                TinyTransformer, "fit", new=assert_model_is_clone,
            ), patch(
                "skeleton.app.local_ai_improvement._token_weighted_perplexity",
                side_effect=[4.0, 3.0, 3.0],
            ), patch(
                "skeleton.app.local_ai_benchmark.compare_benchmark_results",
                return_value={"passes_local_regression_gate": True},
            ):
                receipt = improve_local_model(
                    source, train, heldout, dest, protected_suite=suite,
                )
            self.assertTrue(dest.exists())
            self.assertTrue(receipt.protected_suite_passed)
            retained[0].assert_identity()
            self.assertNotEqual(
                load_native_checkpoint(dest).model_digest,
                retained[0].model_digest,
            )

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
