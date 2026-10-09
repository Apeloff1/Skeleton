"""Multi-category, weighted, model-bound offline benchmark acceptance."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from skeleton.ai.model_runtime import NativeLLMRuntime
from skeleton.ai.runtime.inference.artifact import write_local_model_artifact
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
from skeleton.app.local_ai_benchmark import (
    SCHEMA, MAX_SUITE_BYTES, OfflineBenchmarkError,
    benchmark_native_models, load_benchmark_suite,
)
from skeleton.app.local_ai import load_native_checkpoint
from skeleton.cortex.transformer import TinyTransformer


VOCAB = ("hello", "world", "alpha", "beta", "user", "assistant", "gamma")


def _model(seed: int, vocab=VOCAB) -> NativeRuntimeLocalModel:
    model = TinyTransformer(
        vocab=vocab, dim=8, ctx=64, seed=seed, n_heads=2,
        n_layers=1, d_ff=16,
    )
    return NativeRuntimeLocalModel(NativeLLMRuntime(model))


def _suite() -> dict:
    return {
        "schema": SCHEMA,
        "cases": [
            {"id": "reason-a", "category": "reason", "text": "hello world alpha"},
            {"id": "reason-b", "category": "reason", "text": "world hello alpha"},
            {"id": "dialog-a", "category": "dialog", "text": "hello world beta"},
            {"id": "dialog-b", "category": "dialog", "text": "world hello beta"},
        ],
    }


class TestOfflineBenchmark(unittest.TestCase):
    def _setup(self, directory):
        root = Path(directory)
        baseline = root / "baseline.json"
        candidate = root / "candidate.json"
        suite = root / "suite.json"
        write_local_model_artifact(_model(7), baseline)
        write_local_model_artifact(_model(17), candidate)
        suite.write_text(json.dumps(_suite()), encoding="utf-8")
        return baseline, candidate, suite

    def test_actual_native_weights_evaluate_in_multiple_categories(self):
        with tempfile.TemporaryDirectory() as directory:
            parent, candidate, suite = self._setup(directory)
            report = benchmark_native_models(suite, baseline=parent)
            self.assertEqual(report["schema"], SCHEMA)
            self.assertEqual(report["category_count"], 2)
            self.assertEqual(report["case_count"], 4)
            self.assertEqual(report["predicted_tokens"], 8)
            self.assertGreater(report["baseline"]["overall_perplexity"], 0)
            self.assertEqual(
                set(report["baseline"]["category_scores"]), {"reason", "dialog"},
            )
            self.assertIsNone(report["passes_local_regression_gate"])
            self.assertIsNone(report["candidate"])
            self.assertFalse(report["candidate_promoted"])
            self.assertFalse(report["model_quality_certified"])
            self.assertEqual(report["baseline"]["model_digest"], load_native_checkpoint(parent).model_digest)

    def test_candidate_passes_when_every_category_improves(self):
        with tempfile.TemporaryDirectory() as directory:
            parent, candidate, suite = self._setup(directory)
            with patch.object(
                TinyTransformer, "logprob",
                side_effect=[-math.log(4)] * 4 + [-math.log(2)] * 4,
            ):
                verdict = benchmark_native_models(suite, baseline=parent, candidate=candidate)
            self.assertTrue(verdict["overall_improves"])
            self.assertTrue(verdict["passes_local_regression_gate"])
            self.assertTrue(all(
                x["perplexity_nonregression"] for x in verdict["category_comparisons"].values()
            ))
            self.assertEqual(verdict["baseline"]["overall_perplexity"], 4.0)
            self.assertEqual(verdict["candidate"]["overall_perplexity"], 2.0)

    def test_aggregate_improvement_cannot_mask_category_regression(self):
        with tempfile.TemporaryDirectory() as directory:
            parent, candidate, suite = self._setup(directory)
            with patch.object(
                TinyTransformer, "logprob",
                side_effect=[
                    -math.log(5), -math.log(5), -math.log(2), -math.log(2),
                    -math.log(2), -math.log(2), -math.log(4), -math.log(4),
                ],
            ):
                result = benchmark_native_models(suite, baseline=parent, candidate=candidate)
            self.assertTrue(result["overall_improves"])
            self.assertFalse(result["passes_local_regression_gate"])
            self.assertFalse(result["category_comparisons"]["dialog"]["perplexity_nonregression"])
            self.assertTrue(result["category_comparisons"]["reason"]["perplexity_nonregression"])

    def test_next_token_accuracy_regression_rejects_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            parent, candidate, suite = self._setup(directory)
            manifest = _suite()
            manifest["cases"][0]["expected_next"] = "hello"
            suite.write_text(json.dumps(manifest), encoding="utf-8")
            vocab = load_native_checkpoint(parent).runtime.model.itos
            correct = [0.0] * len(vocab)
            correct[vocab.index("hello")] = 10.0
            incorrect = [0.0] * len(vocab)
            incorrect[vocab.index("world")] = 10.0
            with patch.object(
                TinyTransformer, "logprob",
                side_effect=[-math.log(4)] * 4 + [-math.log(2)] * 4,
            ), patch.object(
                TinyTransformer, "_logits", side_effect=[correct, incorrect],
            ):
                result = benchmark_native_models(suite, baseline=parent, candidate=candidate)
            self.assertTrue(result["overall_improves"])
            self.assertFalse(result["passes_local_regression_gate"])
            self.assertEqual(result["baseline"]["category_scores"]["reason"]["next_token_correct"], 1)
            self.assertEqual(result["candidate"]["category_scores"]["reason"]["next_token_correct"], 0)

    def test_cli_suite_gate_improving_and_regressing_exit_codes(self):
        from skeleton.app.cli import run_app_cli

        with tempfile.TemporaryDirectory() as directory:
            parent, candidate, suite = self._setup(directory)
            out = StringIO()
            with patch.object(
                TinyTransformer, "logprob",
                side_effect=[-math.log(4)] * 4 + [-math.log(2)] * 4,
            ), redirect_stdout(out):
                status = run_app_cli([
                    "local-ai", "--benchmark-suite", str(suite),
                    "--model", str(parent), "--candidate-model", str(candidate), "--json",
                ])
            self.assertEqual(status, 0, out.getvalue())
            self.assertTrue(json.loads(out.getvalue())["passes_local_regression_gate"])
            out = StringIO()
            with patch.object(
                TinyTransformer, "logprob",
                side_effect=[-math.log(2)] * 4 + [-math.log(4)] * 4,
            ), redirect_stdout(out):
                status = run_app_cli([
                    "local-ai", "--benchmark-suite", str(suite),
                    "--model", str(parent), "--candidate-model", str(candidate), "--json",
                ])
            self.assertEqual(status, 1)
            self.assertFalse(json.loads(out.getvalue())["passes_local_regression_gate"])

    def test_strict_json_and_unknown_fields_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            parent, _, suite = self._setup(directory)
            for raw in (
                '{"schema":"x","schema":"y","cases":[]}',
                '{"schema":NaN,"cases":[]}',
                '{"schema":"skeleton.ai.offline.benchmark.v1","cases":[]}',
                '{"schema":"skeleton.ai.offline.benchmark.v1","cases":[{"id":"a","category":"x","text":"hello world","unknown":1}]}',
            ):
                with self.subTest(raw=raw[:55]):
                    suite.write_text(raw, encoding="utf-8")
                    with self.assertRaises(OfflineBenchmarkError):
                        load_benchmark_suite(suite, backend=load_native_checkpoint(parent))

    def test_duplicate_normalized_tokens_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            parent, _, suite = self._setup(directory)
            manifest = _suite()
            manifest["cases"][1]["text"] = "HELLO, WORLD! alpha"
            suite.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(OfflineBenchmarkError, "duplicate normalized"):
                load_benchmark_suite(suite, backend=load_native_checkpoint(parent))

    def test_unsupported_vocabulary_rejected_without_artifact_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            parent, candidate, suite = self._setup(directory)
            base = parent.read_bytes()
            other = candidate.read_bytes()
            manifest = _suite()
            manifest["cases"][0]["text"] = "unknownword one two"
            suite.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(OfflineBenchmarkError, "out-of-vocabulary"):
                benchmark_native_models(suite, baseline=parent, candidate=candidate)
            self.assertEqual(parent.read_bytes(), base)
            self.assertEqual(candidate.read_bytes(), other)

    def test_symlinks_and_oversized_files_rejected_before_read(self):
        with tempfile.TemporaryDirectory() as directory:
            parent, _, suite = self._setup(directory)
            link = Path(directory) / "link.json"
            try:
                link.symlink_to(suite)
            except OSError:
                self.skipTest("symlink creation unavailable")
            with self.assertRaises(OfflineBenchmarkError):
                load_benchmark_suite(link, backend=load_native_checkpoint(parent))
            with suite.open("wb") as out:
                out.seek(MAX_SUITE_BYTES)
                out.write(b"!")
            with patch("os.open", side_effect=AssertionError("oversized suite must not be opened")):
                with self.assertRaises(OfflineBenchmarkError):
                    load_benchmark_suite(suite, backend=load_native_checkpoint(parent))

    def test_candidate_must_use_exact_tokenizer(self):
        with tempfile.TemporaryDirectory() as directory:
            parent, candidate, suite = self._setup(directory)
            candidate.unlink()
            write_local_model_artifact(_model(23, vocab=VOCAB + ("foreign",)), candidate)
            with self.assertRaisesRegex(OfflineBenchmarkError, "tokenizer identity"):
                benchmark_native_models(suite, baseline=parent, candidate=candidate)

    def test_cli_rejects_mixed_modes_and_unbound_suite(self):
        from skeleton.app.cli import run_app_cli

        bad = (
            ["--benchmark-suite", "suite.json"],
            ["--benchmark-suite", "suite.json", "--model", "x", "--prompt", "hello"],
            ["--benchmark-suite", "suite.json", "--model", "x", "--compare-model", "x"],
            ["--benchmark-suite", "suite.json", "--model", "x", "--train-corpus", "x"],
        )
        for flags in bad:
            with self.subTest(flags=flags):
                with redirect_stdout(StringIO()):
                    self.assertEqual(run_app_cli(["local-ai", *flags]), 2)


if __name__ == "__main__":
    unittest.main()
