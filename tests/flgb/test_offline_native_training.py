"""End-to-end local text -> genuine CPU-trained transformer -> artifact -> inference."""
from __future__ import annotations

import asyncio
import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from skeleton.app.local_ai import OfflineAISession, load_native_checkpoint
from skeleton.app.local_ai_training import (
    MAX_CORPUS_BYTES,
    MAX_TRAINING_TOKENS,
    OfflineTrainingError,
    train_local_text,
)


class TestOfflineNativeTraining(unittest.TestCase):
    def test_text_trains_actual_weights_and_restores_native_runtime(self) -> None:
        from skeleton.app.cli import run_app_cli

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "notes.txt"
            artifact = Path(directory) / "model.json"
            source.write_text(
                "user: hello assistant: world\n"
                "user: world assistant: hello\n",
                encoding="utf-8",
            )
            output = StringIO()
            with redirect_stdout(output):
                status = run_app_cli([
                    "local-ai", "--train-corpus", str(source),
                    "--output-model", str(artifact), "--epochs", "1", "--json",
                ])
            self.assertEqual(status, 0, output.getvalue())
            receipt = json.loads(output.getvalue())
            self.assertGreater(receipt["training_steps"], 0)
            self.assertGreater(receipt["training_tokens"], 0)
            self.assertGreater(receipt["initial_perplexity"], 0)
            self.assertGreater(receipt["final_perplexity"], 0)
            self.assertIsInstance(receipt["training_loss_improved"], bool)
            self.assertEqual(len(receipt["checkpoint_sha256"]), 64)
            self.assertFalse(receipt["foundation_model"])
            self.assertFalse(receipt["model_quality_certified"])
            runtime = load_native_checkpoint(artifact)
            self.assertEqual(runtime.model_digest, receipt["model_digest"])
            self.assertEqual(runtime.tokenizer_digest, receipt["tokenizer_digest"])
            reply = asyncio.run(
                OfflineAISession(runtime).ask("user: hello", max_output_tokens=2)
            )
            self.assertTrue(reply.text)
            self.assertEqual(reply.model_digest, receipt["model_digest"])

    def test_rejects_missing_corpus_bad_epochs_and_checkpoint_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "corpus.txt"
            artifact = Path(directory) / "model.json"
            artifact.write_text("existing", encoding="utf-8")
            source.write_text("hello world", encoding="utf-8")
            for epochs in (0, 5, True):
                with self.subTest(epochs=epochs):
                    with self.assertRaises(OfflineTrainingError):
                        train_local_text(source, artifact, epochs=epochs)
            with self.assertRaisesRegex(OfflineTrainingError, "already exists"):
                train_local_text(source, artifact)
            self.assertEqual(artifact.read_text(encoding="utf-8"), "existing")
            with self.assertRaises(OfflineTrainingError):
                train_local_text(Path(directory) / "missing.txt", Path(directory) / "absent.json")

    def test_rejects_too_large_corpus_before_open(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "oversized.txt"
            with source.open("wb") as out:
                out.seek(MAX_CORPUS_BYTES)
                out.write(b".")
            with patch("os.open", side_effect=AssertionError("oversize read forbidden")):
                with self.assertRaises(OfflineTrainingError):
                    train_local_text(source, Path(directory) / "model.json")

    def test_rejects_large_token_count_and_corrupt_encoding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "notes.txt"
            output = Path(directory) / "new.json"
            source.write_text("hello world " * (MAX_TRAINING_TOKENS + 1), encoding="utf-8")
            with self.assertRaisesRegex(OfflineTrainingError, "exceeds 512 tokens"):
                train_local_text(source, output)
            self.assertFalse(output.exists())
            source.write_bytes(b"\xff\xfe\x00\x00")
            with self.assertRaisesRegex(OfflineTrainingError, "UTF-8"):
                train_local_text(source, output)

    def test_installed_windows_exe_route_executes_real_local_ai_cli(self) -> None:
        # This command path must work without invoking Docker, Python scripts,
        # desktop Tk or the Windows-only graphical launcher on a Linux runner.
        from skeleton.app.windows_launcher import main as exe_main

        with tempfile.TemporaryDirectory() as directory:
            corpus = Path(directory) / "notes.txt"
            checkpoint = Path(directory) / "checkpoint.json"
            corpus.write_text(
                "user hello assistant world\n"
                "user world assistant hello\n",
                encoding="utf-8",
            )
            output = StringIO()
            with redirect_stdout(output):
                status = exe_main([
                    "--offline-command", "local-ai",
                    "--train-corpus", str(corpus),
                    "--output-model", str(checkpoint), "--json",
                ])
            self.assertEqual(status, 0, output.getvalue())
            self.assertTrue(checkpoint.is_file())
            self.assertGreater(json.loads(output.getvalue())["training_steps"], 0)
            output = StringIO()
            with redirect_stdout(output):
                status = exe_main([
                    "--offline-command", "local-ai",
                    "--model", str(checkpoint), "--inspect-model", "--json",
                ])
            self.assertEqual(status, 0, output.getvalue())
            self.assertTrue(json.loads(output.getvalue())["model_digest"])
            with redirect_stdout(StringIO()):
                self.assertEqual(exe_main([
                    "--offline-command", "status",
                ]), 2)
                self.assertEqual(exe_main(["--offline-command"]), 2)
                self.assertEqual(exe_main([
                    "--full", "--offline-command", "local-ai",
                ]), 2)
                self.assertEqual(exe_main([
                    "--development", "--offline-command", "local-ai",
                ]), 2)

    def test_training_is_explicit_never_implicit_and_requires_output_path(self) -> None:
        from skeleton.app.cli import run_app_cli

        for args in (
            ["local-ai", "--train-corpus", "notes.txt"],
            ["local-ai", "--output-model", "model.json"],
            ["local-ai", "--train-corpus", "notes.txt", "--output-model", "model.json", "--prompt", "hello"],
        ):
            with self.subTest(args=args):
                with redirect_stdout(StringIO()):
                    self.assertEqual(run_app_cli(args), 2)


if __name__ == "__main__":
    unittest.main()
