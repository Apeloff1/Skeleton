"""Headless local chat CLI: real native inference and durable model-specific management."""
from __future__ import annotations

from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.offline_chat import OfflineChatStore
from skeleton.app.offline_chat_cli import main
from skeleton.cortex.transformer import TinyTransformer


class HeadlessOfflineChatTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.model_path = self.directory / "native-model.json"
        self.database = self.directory / "model.sqlite3"
        runtime = NativeLLMRuntime(TinyTransformer(
            vocab=("system:", "user:", "assistant:", "hello", "world", "answer"),
            dim=8, ctx=96, seed=41, n_heads=2, n_layers=2, d_ff=16,
        ))
        self.model_digest = runtime.model_digest
        self.tokenizer_digest = runtime.tokenizer.digest
        self.model_path.write_text(runtime.checkpoint_json(), encoding="utf-8")

    def _run(self, *args: str) -> tuple[int, str, str]:
        stdout = StringIO()
        stderr = StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = main([
                "--native-checkpoint", str(self.model_path),
                "--database", str(self.database),
                *args,
            ])
        return status, stdout.getvalue(), stderr.getvalue()

    def test_full_local_chat_and_backup_management(self):
        code, output, errors = self._run(
            "--message", "hello", "--max-output-tokens", "2", "--json"
        )
        self.assertEqual(code, 0, errors)
        receipt = json.loads(output)
        self.assertEqual(receipt["model_digest"], self.model_digest)
        self.assertEqual(len(receipt["execution_receipt_digest"]), 64)
        sid = receipt["session_id"]
        self.assertEqual(receipt["output_tokens"], 2)
        code, output, errors = self._run("--list", "--json")
        self.assertEqual(code, 0, errors)
        self.assertEqual(json.loads(output), [{"session_id": sid, "revision": 1}])
        backup = self.directory / "private.json"
        code, output, errors = self._run(
            "--export-session", sid, "--output", str(backup)
        )
        self.assertEqual(code, 0, errors)
        self.assertTrue(backup.is_file())
        code, output, errors = self._run(
            "--import-bundle", str(backup)
        )
        self.assertEqual(code, 0, errors)
        imported_sid = json.loads(output)["imported_session_id"]
        self.assertNotEqual(imported_sid, sid)
        code, output, errors = self._run(
            "--session", imported_sid, "--message", "world",
            "--max-output-tokens", "2", "--json"
        )
        self.assertEqual(code, 0, errors)
        self.assertEqual(json.loads(output)["session_id"], imported_sid)
        code, output, errors = self._run("--delete-session", sid)
        self.assertEqual(code, 0, errors)
        code, output, errors = self._run("--list", "--json")
        self.assertEqual(code, 0, errors)
        self.assertEqual(
            json.loads(output), [{"session_id": imported_sid, "revision": 2}]
        )

    def test_headless_fork_branches_without_reexecuting_parent(self):
        code, output, errors = self._run(
            "--message", "hello", "--max-output-tokens", "2", "--json"
        )
        self.assertEqual(code, 0, errors)
        parent = json.loads(output)["session_id"]
        code, output, errors = self._run(
            "--fork-session", parent, "--fork-after-turn", "0"
        )
        self.assertEqual(code, 0, errors)
        fork = json.loads(output)["forked_session_id"]
        self.assertNotEqual(parent, fork)
        code, output, errors = self._run("--list", "--json")
        self.assertEqual(code, 0, errors)
        self.assertEqual(
            {x["session_id"]: x["revision"] for x in json.loads(output)},
            {parent: 1, fork: 0},
        )
        code, output, errors = self._run(
            "--session", fork, "--message", "world",
            "--max-output-tokens", "2", "--json"
        )
        self.assertEqual(code, 0, errors)
        code, output, errors = self._run("--list", "--json")
        self.assertEqual(code, 0, errors)
        self.assertEqual(
            {x["session_id"]: x["revision"] for x in json.loads(output)},
            {parent: 1, fork: 1},
        )

    def test_listing_empty_store_does_not_create_phantom_session(self):
        code, output, errors = self._run("--list", "--json")
        self.assertEqual(code, 0, errors)
        self.assertEqual(json.loads(output), [])
        with OfflineChatStore(self.database) as store:
            self.assertEqual(store.list_sessions(
                self.model_digest, self.tokenizer_digest
            ), ())

    def test_invalid_session_and_missing_backup_fail_closed(self):
        code, output, errors = self._run(
            "--session", "not-real", "--message", "hello",
            "--max-output-tokens", "2"
        )
        self.assertEqual(code, 1)
        code, output, errors = self._run(
            "--import-bundle", str(self.directory / "missing.json")
        )
        self.assertEqual(code, 1)
        code, output, errors = self._run("--list", "--json")
        self.assertEqual(code, 0, errors)
        self.assertEqual(json.loads(output), [])

    def test_cli_native_offline_run_requires_no_hosted_provider(self):
        from unittest.mock import patch
        with patch.dict("os.environ", {
            "OPENAI_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
        }):
            code, output, errors = self._run(
                "--message", "hello", "--max-output-tokens", "2", "--json"
            )
        self.assertEqual(code, 0, errors)
        self.assertTrue(json.loads(output)["text"])


if __name__ == "__main__":
    unittest.main()
