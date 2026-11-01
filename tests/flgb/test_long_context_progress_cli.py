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

    def test_lazy_runtime_export_is_bound_to_same_contract(self):
        self.assertEqual(LongContextProgressHead.__module__,
                         "skeleton.ai.model_runtime.long_context_progress")


if __name__ == "__main__":
    unittest.main()
