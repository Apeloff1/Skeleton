"""Source-backed offline long-context custody and crash recovery tests."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from hashlib import sha256
from io import StringIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from skeleton.ai.model_runtime import LongContextSpool
from skeleton.ai.model_runtime.flgb_model_runtime import TokenSequence
from skeleton.ai.model_runtime.long_context_cli import main as cli_main
from skeleton.ai.model_runtime.long_context_spool import LongContextSpoolError
from skeleton.ai.model_runtime.tokenization import serialize_token_sequence

TOKENIZER = sha256(b"original native tokenizer").hexdigest()
SOURCE = sha256(b"original authored story").hexdigest()


class TestLongContextSpool(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / "spool"
        self.spool = LongContextSpool(self.root, disk_reserve_bytes=0)
        self.sequence = TokenSequence(TOKENIZER, tuple(range(30)), SOURCE)

    def stage(self):
        return self.spool.stage(self.sequence)

    def test_stage_and_resume_across_process_object(self):
        start = self.stage()
        restored = LongContextSpool(self.root, disk_reserve_bytes=0)
        receipt, sequence = restored.load(start, expected_tokenizer_digest=TOKENIZER)
        self.assertEqual(receipt.cursor, 0)
        self.assertEqual(sequence, self.sequence)
        self.assertEqual(restored.stage(self.sequence), start)

    def test_bounded_windows_and_explicit_progress(self):
        current = self.stage()
        for expected_start in (0, 8, 16, 24):
            window = self.spool.next_window(current,
                expected_tokenizer_digest=TOKENIZER, max_tokens=8)
            self.assertEqual(window.start, expected_start)
            self.assertEqual(window.source_sequence_digest, self.sequence.digest)
            current = self.spool.advance(current,
                expected_tokenizer_digest=TOKENIZER, consumed_tokens=len(window.token_ids))
        self.assertIsNone(self.spool.next_window(current,
            expected_tokenizer_digest=TOKENIZER, max_tokens=8))

    def test_immutable_branching_from_same_parent(self):
        start = self.stage()
        a = self.spool.advance(start, expected_tokenizer_digest=TOKENIZER, consumed_tokens=1)
        b = self.spool.advance(start, expected_tokenizer_digest=TOKENIZER, consumed_tokens=2)
        self.assertNotEqual(a, b)
        self.assertEqual(self.spool.load(start, expected_tokenizer_digest=TOKENIZER)[0].cursor, 0)
        self.assertEqual(self.spool.load(a, expected_tokenizer_digest=TOKENIZER)[0].cursor, 1)

    def test_concurrent_identical_stage_is_idempotent(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.stage(), range(8)))
        self.assertEqual(len(set(results)), 1)

    def test_reject_tokenizer_identity_drift(self):
        start = self.stage()
        with self.assertRaises(LongContextSpoolError):
            self.spool.load(start, expected_tokenizer_digest=SOURCE)

    def test_reject_mutated_sequence_bytes(self):
        start = self.stage()
        receipt, _ = self.spool.load(start, expected_tokenizer_digest=TOKENIZER)
        path = self.spool._path("object", receipt.object_digest)
        path.write_bytes(b"corrupt")
        with self.assertRaises(LongContextSpoolError):
            self.spool.load(start, expected_tokenizer_digest=TOKENIZER)

    def test_reject_mutated_checkpoint_bytes(self):
        start = self.stage()
        path = self.spool._path("checkpoint", start)
        data = json.loads(path.read_text())
        data["cursor"] = 7
        path.write_text(json.dumps(data))
        with self.assertRaises(LongContextSpoolError):
            self.spool.load(start, expected_tokenizer_digest=TOKENIZER)

    def test_reject_missing_parent(self):
        start = self.stage()
        child = self.spool.advance(start, expected_tokenizer_digest=TOKENIZER, consumed_tokens=1)
        self.spool._path("checkpoint", start).unlink()
        with self.assertRaises(LongContextSpoolError):
            self.spool.load(child, expected_tokenizer_digest=TOKENIZER)

    def test_reject_overadvance_and_invalid_types(self):
        start = self.stage()
        for value in (0, -1, True, 31):
            with self.subTest(value=value), self.assertRaises(LongContextSpoolError):
                self.spool.advance(start, expected_tokenizer_digest=TOKENIZER,
                                   consumed_tokens=value)

    def test_reject_tight_disk_reserve(self):
        blocked = LongContextSpool(self.root / "reserved", disk_reserve_bytes=2**60)
        with self.assertRaises(LongContextSpoolError):
            blocked.stage(self.sequence)

    def test_reject_symlinked_object(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlink unavailable")
        start = self.stage()
        receipt, _ = self.spool.load(start, expected_tokenizer_digest=TOKENIZER)
        path = self.spool._path("object", receipt.object_digest)
        saved = path.with_name("original")
        path.rename(saved)
        try:
            path.symlink_to(saved)
        except (OSError, NotImplementedError):
            self.skipTest("symlink permission unavailable")
        with self.assertRaises(LongContextSpoolError):
            self.spool.load(start, expected_tokenizer_digest=TOKENIZER)

    def test_reject_symlinked_root(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlink unavailable")
        link = Path(self.directory.name) / "link"
        try:
            link.symlink_to(self.root, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlink permission unavailable")
        with self.assertRaises(LongContextSpoolError):
            LongContextSpool(link)

    def test_cli_stage_inspect_window_advance(self):
        sequence_file = Path(self.directory.name) / "tokens.json"
        sequence_file.write_bytes(serialize_token_sequence(self.sequence))
        def invoke(*args):
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(cli_main(["--root", str(self.root),
                    "--tokenizer-digest", TOKENIZER, *args]), 0)
            return json.loads(output.getvalue())
        start = invoke("stage", "--sequence-file", str(sequence_file))["checkpoint"]
        self.assertEqual(invoke("inspect", "--checkpoint", start)["total_tokens"], 30)
        self.assertEqual(invoke("window", "--checkpoint", start,
                                "--max-tokens", "3")["window"]["token_ids"], [0, 1, 2])
        child = invoke("advance", "--checkpoint", start,
                       "--consumed-tokens", "3")["checkpoint"]
        self.assertEqual(invoke("window", "--checkpoint", child,
                                "--max-tokens", "3")["window"]["token_ids"], [3, 4, 5])

    def test_byte_budget_and_invalid_checkpoint(self):
        tiny = LongContextSpool(self.root / "tiny",
            max_sequence_bytes=1, disk_reserve_bytes=0)
        with self.assertRaises(LongContextSpoolError):
            tiny.stage(self.sequence)
        with self.assertRaises(LongContextSpoolError):
            self.spool.load("not-a-digest", expected_tokenizer_digest=TOKENIZER)

    def test_uncommitted_temporary_file_does_not_change_resume(self):
        start = self.stage()
        path = self.spool._path("checkpoint", start)
        (path.parent / ".interrupted.tmp").write_bytes(b"partial")
        self.assertEqual(self.spool.load(start, expected_tokenizer_digest=TOKENIZER)[0].cursor, 0)


if __name__ == "__main__":
    unittest.main()
