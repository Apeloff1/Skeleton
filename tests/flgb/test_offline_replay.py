"""Independent deterministic replay of native learned checkpoint evidence."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from skeleton.app.local_ai_improvement import improve_local_model
from skeleton.app.local_ai_replay import (
    MAX_RECEIPT_BYTES, OfflineReplayError, replay_local_improvement,
)
from skeleton.ai.model_runtime import NativeLLMRuntime
from skeleton.ai.runtime.inference.artifact import write_local_model_artifact
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
from skeleton.cortex.transformer import TinyTransformer


class TestOfflineReplay(unittest.TestCase):
    def _accepted(self, directory: str):
        root = Path(directory)
        parent = root / "base.json"
        training = root / "train.txt"
        heldout = root / "heldout.txt"
        candidate = root / "candidate.json"
        model = TinyTransformer(
            vocab=("user", "assistant", "hello", "world", "alpha", "beta"),
            dim=8, ctx=96, seed=37, n_heads=2, n_layers=2, d_ff=16,
        )
        write_local_model_artifact(
            NativeRuntimeLocalModel(NativeLLMRuntime(model)), parent,
        )
        training.write_text(
            "user hello assistant world alpha\n" * 4, encoding="utf-8",
        )
        heldout.write_text(
            "user hello assistant world beta\n", encoding="utf-8",
        )
        with patch(
            "skeleton.app.local_ai_improvement._token_weighted_perplexity",
            side_effect=[4.0, 3.0, 3.0],
        ):
            receipt = improve_local_model(parent, training, heldout, candidate, epochs=1)
        record = Path(directory) / "accepted-receipt.json"
        record.write_text(json.dumps(receipt.to_dict(), sort_keys=True), encoding="utf-8")
        return parent, training, heldout, candidate, record

    def test_replays_real_native_training_to_identical_weights(self):
        with tempfile.TemporaryDirectory() as directory:
            parent, train, heldout, candidate, receipt = self._accepted(directory)
            previous = parent.read_bytes()
            accepted = candidate.read_bytes()
            with patch(
                "skeleton.app.local_ai_improvement._token_weighted_perplexity",
                side_effect=[4.0, 3.0, 3.0],
            ):
                replayed = replay_local_improvement(
                    receipt, parent, candidate, train, heldout,
                )
            self.assertTrue(replayed["reproducible"])
            self.assertFalse(replayed["model_promoted"])
            self.assertFalse(replayed["model_quality_certified"])
            self.assertEqual(len(replayed["receipt_sha256"]), 64)
            self.assertEqual(parent.read_bytes(), previous)
            self.assertEqual(candidate.read_bytes(), accepted)

    def test_candidate_identity_drift_rejected_before_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            parent, train, heldout, candidate, receipt = self._accepted(directory)
            item = json.loads(receipt.read_text(encoding="utf-8"))
            item["candidate_model_digest"] = "0" * 64
            receipt.write_text(json.dumps(item), encoding="utf-8")
            with self.assertRaisesRegex(OfflineReplayError, "checkpoint identity"):
                replay_local_improvement(receipt, parent, candidate, train, heldout)

    def test_replay_checks_source_identity_not_just_model_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            parent, train, heldout, candidate, receipt = self._accepted(directory)
            train.write_text("user hello assistant beta\n", encoding="utf-8")
            with patch(
                "skeleton.app.local_ai_improvement._token_weighted_perplexity",
                side_effect=[4.0, 3.0, 3.0],
            ):
                with self.assertRaisesRegex(OfflineReplayError, "replay evidence mismatch"):
                    replay_local_improvement(receipt, parent, candidate, train, heldout)

    def test_nonfinite_duplicate_and_unknown_receipts_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            parent, train, heldout, candidate, receipt = self._accepted(directory)
            valid = receipt.read_text(encoding="utf-8")
            for corrupt in (
                valid.replace('"schema_version":', '"schema_version":1,"schema_version":'),
                valid.replace('"schema_version":', '"unknown": NaN,"schema_version":'),
                valid.replace('"schema_version":', '"unbounded":42,"schema_version":'),
            ):
                with self.subTest(prefix=corrupt[:32]):
                    receipt.write_text(corrupt, encoding="utf-8")
                    with self.assertRaises(OfflineReplayError):
                        replay_local_improvement(receipt, parent, candidate, train, heldout)

    def test_receipt_symlink_and_oversized_file_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            parent, train, heldout, candidate, receipt = self._accepted(directory)
            link = Path(directory) / "link.json"
            try:
                link.symlink_to(receipt)
            except OSError:
                self.skipTest("symlinks unavailable")
            with self.assertRaises(OfflineReplayError):
                replay_local_improvement(link, parent, candidate, train, heldout)
            with receipt.open("wb") as stream:
                stream.seek(MAX_RECEIPT_BYTES)
                stream.write(b".")
            with patch("os.open", side_effect=AssertionError("oversized receipt must not be read")):
                with self.assertRaises(OfflineReplayError):
                    replay_local_improvement(receipt, parent, candidate, train, heldout)

    def test_cli_replay_requires_full_explicit_evidence(self):
        from skeleton.app.cli import run_app_cli

        with redirect_stdout(StringIO()):
            code = run_app_cli([
                "local-ai", "--replay-improvement", "receipt.json",
                "--compare-model", "parent.json",
            ])
        self.assertEqual(code, 2)

    def test_cli_replay_verifies_authentic_receipt(self):
        from skeleton.app.cli import run_app_cli

        with tempfile.TemporaryDirectory() as directory:
            parent, train, heldout, candidate, receipt = self._accepted(directory)
            out = StringIO()
            with patch(
                "skeleton.app.local_ai_improvement._token_weighted_perplexity",
                side_effect=[4.0, 3.0, 3.0],
            ), redirect_stdout(out):
                code = run_app_cli([
                    "local-ai", "--replay-improvement", str(receipt),
                    "--compare-model", str(parent), "--candidate-model", str(candidate),
                    "--train-corpus", str(train), "--eval-corpus", str(heldout),
                    "--json",
                ])
            self.assertEqual(code, 0, out.getvalue())
            report = json.loads(out.getvalue())
            self.assertTrue(report["reproducible"])
            self.assertFalse(report["model_promoted"])


if __name__ == "__main__":
    unittest.main()
