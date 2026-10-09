"""Executable integration coverage for the Docker-free desktop native AI path."""
from __future__ import annotations

import asyncio
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from skeleton.ai.model_runtime import NativeLLMRuntime
from skeleton.ai.runtime.inference.artifact import LocalModelArtifactError, write_local_model_artifact
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
from skeleton.app.local_ai import OfflineAIError, OfflineAISession, load_native_checkpoint
from skeleton.cortex.transformer import TinyTransformer


def backend(*, ctx: int = 96) -> NativeRuntimeLocalModel:
    model = TinyTransformer(
        vocab=("system:", "user:", "assistant:", "hello", "world", "alpha", "beta", "answer"),
        dim=8,
        ctx=ctx,
        seed=37,
        n_heads=2,
        n_layers=2,
        d_ff=16,
    )
    return NativeRuntimeLocalModel(NativeLLMRuntime(model))


class TestOfflineDesktopAI(unittest.TestCase):
    def test_bundled_native_inference_smoke_graph(self):
        from skeleton.app.local_ai import smoke_offline_native_inference

        self.assertTrue(smoke_offline_native_inference())

    def test_checkpoint_load_and_native_generation_without_providers(self):
        with tempfile.TemporaryDirectory() as directory:
            model_path = Path(directory) / "local.json"
            expected = backend()
            write_local_model_artifact(expected, model_path)
            loaded = load_native_checkpoint(model_path)
            self.assertEqual(loaded.model_digest, expected.model_digest)
            self.assertEqual(loaded.tokenizer_digest, expected.tokenizer_digest)
            session = OfflineAISession(loaded)
            with patch.dict("os.environ", {"OPENAI_API_KEY": "", "AI_PROVIDER": "local"}):
                answer = asyncio.run(session.ask("hello", max_output_tokens=3))
            self.assertTrue(answer.text)
            self.assertEqual(answer.model_digest, expected.model_digest)
            self.assertEqual(len(answer.execution_receipt_digest), 64)
            self.assertEqual(len(session.history), 2)
            self.assertEqual(session.history[0], ("user", "hello"))
            self.assertEqual(session.history[1], ("assistant", answer.text))
            session.clear()
            self.assertEqual(session.history, ())

    def test_generation_error_does_not_commit_any_conversation_state(self):
        session = OfflineAISession(backend())

        async def fail(_request):
            raise RuntimeError("model failed before terminal receipt")

        session.engine.generate = fail
        with self.assertRaisesRegex(RuntimeError, "model failed"):
            asyncio.run(session.ask("hello", max_output_tokens=2))
        self.assertEqual(session.history, ())

    def test_only_full_oldest_turns_dropped_for_bounded_context(self):
        session = OfflineAISession(backend(ctx=48))
        session.history = (
            ("user", "alpha " * 70),
            ("assistant", "alpha " * 70),
            ("user", "hello"),
            ("assistant", "answer"),
        )
        request, kept = session._request("hello", 2)
        self.assertEqual(kept, (("user", "hello"), ("assistant", "answer")))
        self.assertEqual(request.history, kept)
        self.assertEqual(session.history[0][0], "user")  # pruning is not a write

    def test_invalid_prompts_and_output_budgets_rejected(self):
        session = OfflineAISession(backend())
        for prompt in ("", " ", "a" * 4097):
            with self.subTest(prompt_length=len(prompt)):
                with self.assertRaises(OfflineAIError):
                    asyncio.run(session.ask(prompt, max_output_tokens=2))
        for budget in (0, True, 100000):
            with self.subTest(budget=budget):
                with self.assertRaises(OfflineAIError):
                    asyncio.run(session.ask("hello", max_output_tokens=budget))
        self.assertEqual(session.history, ())

    def test_bad_artifacts_fail_without_using_demo_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "native.json"
            path.write_text('{"schema":"x","schema":"y"}', encoding="utf-8")
            with self.assertRaises(LocalModelArtifactError):
                load_native_checkpoint(path)
            path.write_text('{"kind":"reference_ngram","model_id":"x"}', encoding="utf-8")
            with self.assertRaises((LocalModelArtifactError, OfflineAIError)):
                load_native_checkpoint(path)

    def test_large_artifacts_rejected_before_reading_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "oversized.json"
            with path.open("wb") as handle:
                handle.seek(128 * 1024 * 1024)
                handle.write(b"!")
            with patch.object(Path, "open", side_effect=AssertionError("must not read oversized file")):
                with self.assertRaises(LocalModelArtifactError):
                    load_native_checkpoint(path)

    def test_headless_app_cli_executes_native_model_without_docker(self):
        from skeleton.app.cli import run_app_cli

        with tempfile.TemporaryDirectory() as directory:
            model_path = Path(directory) / "local.json"
            write_local_model_artifact(backend(), model_path)
            output = StringIO()
            with redirect_stdout(output):
                status = run_app_cli([
                    "local-ai", "--model", str(model_path), "--prompt", "hello",
                    "--max-output-tokens", "2", "--json",
                ])
            self.assertEqual(status, 0, output.getvalue())
            payload = json.loads(output.getvalue())
            self.assertTrue(payload["text"])
            self.assertEqual(len(payload["execution_receipt_digest"]), 64)
            self.assertEqual(payload["output_tokens"], 2)

    def test_headless_inference_requires_explicit_model_and_prompt(self):
        from skeleton.app.cli import run_app_cli

        output = StringIO()
        with redirect_stdout(output):
            status = run_app_cli(["local-ai", "--prompt", "hello"])
        self.assertEqual(status, 2)
        self.assertIn("requires both", output.getvalue())

    def test_symlink_artifact_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "native.json"
            link = Path(directory) / "link.json"
            path.write_text("{}", encoding="utf-8")
            try:
                link.symlink_to(path)
            except OSError:
                self.skipTest("symlink creation unavailable")
            with self.assertRaises(LocalModelArtifactError):
                load_native_checkpoint(link)


if __name__ == "__main__":
    unittest.main()
