"""CLI integration contract for durable offline long-context progress."""
from __future__ import annotations

from contextlib import redirect_stdout
from hashlib import sha256
from io import StringIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.ai.model_runtime import LongContextProgressHead, LongContextSpool
from skeleton.ai.model_runtime.flgb_model_runtime import TokenSequence
from skeleton.ai.model_runtime.long_context_cli import main

TOKENIZER = sha256(b"head-cli-tokenizer").hexdigest()
SOURCE = sha256(b"head-cli-source").hexdigest()


@unittest.skipUnless(os.name == "posix", "POSIX durable head CLI")
class TestLongContextProgressCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "spool"

    def call(self, *args: str) -> dict[str, object]:
        out = StringIO()
        with redirect_stdout(out):
            result = main(["--root", str(self.root),
                           "--tokenizer-digest", TOKENIZER, *args])
        self.assertEqual(result, 0)
        return json.loads(out.getvalue())

    def test_cli_lifecycle_restarts_and_commits_exactly_once(self):
        spool = LongContextSpool(self.root, disk_reserve_bytes=0)
        try:
            genesis = spool.stage(TokenSequence(TOKENIZER, tuple(range(10)), SOURCE))
        finally:
            spool.close()
        first = self.call("head-init", "--stream-id", "story.1",
                          "--checkpoint", genesis)
        self.assertEqual(first["generation"], 0)
        observed = self.call("head-window", "--stream-id", "story.1",
                             "--max-tokens", "3")
        self.assertEqual(observed["window"]["token_ids"], [0, 1, 2])
        self.assertFalse(observed["is_execution_lease"])
        child = self.call("head-advance", "--stream-id", "story.1",
                          "--expected-checkpoint", genesis,
                          "--consumed-tokens", "3")
        self.assertEqual(child["generation"], 1)
        self.assertNotEqual(child["checkpoint_digest"], genesis)
        status = self.call("head-status", "--stream-id", "story.1")
        self.assertEqual(status["checkpoint_digest"], child["checkpoint_digest"])
        self.assertEqual(self.call("head-window", "--stream-id", "story.1",
                                  "--max-tokens", "3")["window"]["token_ids"],
                         [3, 4, 5])
        self.assertEqual(self.call("head-recover")["removed"], 0)

    def test_cli_rejects_stale_progress_without_printing_token_payload(self):
        spool = LongContextSpool(self.root, disk_reserve_bytes=0)
        try:
            genesis = spool.stage(TokenSequence(TOKENIZER, tuple(range(4)), SOURCE))
        finally:
            spool.close()
        self.call("head-init", "--stream-id", "story.1", "--checkpoint", genesis)
        self.call("head-advance", "--stream-id", "story.1",
                  "--expected-checkpoint", genesis, "--consumed-tokens", "1")
        out = StringIO()
        with redirect_stdout(out), self.assertRaises(SystemExit) as caught:
            main(["--root", str(self.root), "--tokenizer-digest", TOKENIZER,
                  "head-advance", "--stream-id", "story.1",
                  "--expected-checkpoint", genesis, "--consumed-tokens", "1"])
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(out.getvalue(), "")


    def test_generation_fenced_window_cli_and_payload_free_inventory(self):
        spool = LongContextSpool(self.root, disk_reserve_bytes=0)
        try:
            genesis = spool.stage(TokenSequence(TOKENIZER, tuple(range(8)), SOURCE))
        finally:
            spool.close()
        self.call("head-init", "--stream-id", "story.2", "--checkpoint", genesis)
        observation = self.call(
            "head-compare-window", "--stream-id", "story.2",
            "--expected-checkpoint", genesis, "--expected-generation", "0",
            "--max-tokens", "3",
        )
        self.assertEqual(observation["window"]["token_ids"], [0, 1, 2])
        self.assertFalse(observation["is_execution_lease"])
        audit_before = self.call("head-audit", "--max-heads", "2")
        self.assertEqual(audit_before["heads_verified"], 1)
        self.assertFalse(audit_before["token_payloads_returned"])
        self.assertNotIn("token_ids", str(audit_before))
        child = self.call(
            "head-commit-window", "--stream-id", "story.2",
            "--expected-checkpoint", genesis, "--expected-generation", "0",
            "--expected-window-digest", observation["window"]["digest"],
            "--max-tokens", "3", "--consumed-tokens", "2",
        )
        self.assertEqual(child["generation"], 1)
        audit_after = self.call("head-audit", "--max-heads", "2")
        self.assertNotEqual(audit_before["inventory_digest"], audit_after["inventory_digest"])
        next_window = self.call(
            "head-compare-window", "--stream-id", "story.2",
            "--expected-checkpoint", child["checkpoint_digest"],
            "--expected-generation", "1", "--max-tokens", "3",
        )
        self.assertEqual(next_window["window"]["token_ids"], [2, 3, 4])

    def test_cli_rejects_stale_window_without_stdout_or_progress(self):
        spool = LongContextSpool(self.root, disk_reserve_bytes=0)
        try:
            genesis = spool.stage(TokenSequence(TOKENIZER, tuple(range(4)), SOURCE))
        finally:
            spool.close()
        self.call("head-init", "--stream-id", "story.3", "--checkpoint", genesis)
        observed = self.call(
            "head-compare-window", "--stream-id", "story.3",
            "--expected-checkpoint", genesis, "--expected-generation", "0",
            "--max-tokens", "2",
        )
        self.call(
            "head-commit-window", "--stream-id", "story.3",
            "--expected-checkpoint", genesis, "--expected-generation", "0",
            "--expected-window-digest", observed["window"]["digest"],
            "--max-tokens", "2", "--consumed-tokens", "1",
        )
        output = StringIO()
        with redirect_stdout(output), self.assertRaises(SystemExit) as caught:
            main(["--root", str(self.root), "--tokenizer-digest", TOKENIZER,
                  "head-commit-window", "--stream-id", "story.3",
                  "--expected-checkpoint", genesis, "--expected-generation", "0",
                  "--expected-window-digest", observed["window"]["digest"],
                  "--max-tokens", "2", "--consumed-tokens", "1"])
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(self.call("head-status", "--stream-id", "story.3")["generation"], 1)

    def test_lazy_runtime_export_is_bound_to_same_contract(self):
        self.assertEqual(LongContextProgressHead.__module__,
                         "skeleton.ai.model_runtime.long_context_progress")


if __name__ == "__main__":
    unittest.main()
