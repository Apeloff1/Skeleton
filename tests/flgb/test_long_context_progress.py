"""Durable linearized long-context stream cursor contract tests."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from skeleton.ai.model_runtime.flgb_model_runtime import TokenSequence
from skeleton.ai.model_runtime.long_context_spool import LongContextSpool, LongContextSpoolError
from skeleton.ai.model_runtime.long_context_progress import LongContextProgressHead

TOKENIZER = sha256(b"head-tokenizer").hexdigest()
SOURCE = sha256(b"head-source").hexdigest()


@unittest.skipUnless(os.name == "posix", "POSIX descriptor-relative custody")
class TestLongContextProgressHead(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.spool = LongContextSpool(Path(self.tmp.name) / "spool", disk_reserve_bytes=0)
        self.addCleanup(self.spool.close)
        self.heads = LongContextProgressHead(self.spool)
        self.genesis = self.spool.stage(TokenSequence(TOKENIZER, tuple(range(16)), SOURCE))

    def init(self):
        return self.heads.initialize("worker.1", self.genesis,
                                     expected_tokenizer_digest=TOKENIZER)

    def test_progress_survives_restart_with_bounded_window(self):
        self.init()
        observed = self.heads.window("worker.1",
            expected_tokenizer_digest=TOKENIZER, max_tokens=4)
        self.assertEqual(observed["window"]["token_ids"], [0, 1, 2, 3])
        self.assertFalse(observed["is_execution_lease"])
        next_head = self.heads.advance("worker.1",
            expected_checkpoint_digest=self.genesis,
            expected_tokenizer_digest=TOKENIZER, consumed_tokens=4)
        self.assertEqual(next_head["generation"], 1)
        restarted = LongContextSpool(self.spool.root, disk_reserve_bytes=0)
        self.addCleanup(restarted.close)
        resumed = LongContextProgressHead(restarted)
        self.assertEqual(resumed.status("worker.1",
            expected_tokenizer_digest=TOKENIZER)["checkpoint_digest"],
            next_head["checkpoint_digest"])
        self.assertEqual(resumed.window("worker.1",
            expected_tokenizer_digest=TOKENIZER, max_tokens=4)["window"]["token_ids"],
            [4, 5, 6, 7])

    def test_stale_progress_fails_without_rewind(self):
        self.init()
        first = self.heads.advance("worker.1", expected_checkpoint_digest=self.genesis,
            expected_tokenizer_digest=TOKENIZER, consumed_tokens=1)
        with self.assertRaisesRegex(LongContextSpoolError, "stale"):
            self.heads.advance("worker.1", expected_checkpoint_digest=self.genesis,
                expected_tokenizer_digest=TOKENIZER, consumed_tokens=1)
        self.assertEqual(self.heads.status("worker.1",
            expected_tokenizer_digest=TOKENIZER)["checkpoint_digest"],
            first["checkpoint_digest"])

    def test_concurrent_writers_only_one_can_commit(self):
        self.init()
        def attempt(_):
            try:
                return self.heads.advance("worker.1",
                    expected_checkpoint_digest=self.genesis,
                    expected_tokenizer_digest=TOKENIZER, consumed_tokens=1)
            except LongContextSpoolError as exc:
                return str(exc)
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(attempt, range(2)))
        self.assertEqual(sum(isinstance(x, dict) for x in outcomes), 1)
        self.assertTrue(any(isinstance(x, str) and "stale" in x for x in outcomes))

    def test_initialize_is_one_use_and_streams_are_isolated(self):
        first = self.init()
        with self.assertRaisesRegex(LongContextSpoolError, "already"):
            self.init()
        second = self.heads.initialize("worker.2", self.genesis,
            expected_tokenizer_digest=TOKENIZER)
        self.assertNotEqual(first["stream_digest"], second["stream_digest"])

    def test_bad_ids_and_consumption_fail_closed(self):
        for value in ("", "../escape", "x" * 129, "x/y", "ñ", "a b"):
            with self.subTest(value=value), self.assertRaises(LongContextSpoolError):
                self.heads.initialize(value, self.genesis,
                    expected_tokenizer_digest=TOKENIZER)
        self.init()
        for value in (0, -1, True, "1", 2**40):
            with self.subTest(value=value), self.assertRaises(LongContextSpoolError):
                self.heads.advance("worker.1", expected_checkpoint_digest=self.genesis,
                    expected_tokenizer_digest=TOKENIZER, consumed_tokens=value)
        with self.assertRaisesRegex(LongContextSpoolError, "tokenizer mismatch"):
            self.heads.status("worker.1", expected_tokenizer_digest=SOURCE)

    def test_corrupt_and_symlink_head_are_denied(self):
        first = self.init()
        path = self.spool.root / "heads" / first["stream_digest"]
        path.write_bytes(b"{}")
        with self.assertRaises(LongContextSpoolError):
            self.heads.status("worker.1", expected_tokenizer_digest=TOKENIZER)
        path.unlink()
        path.symlink_to(self.spool.root / "absent")
        with self.assertRaises(LongContextSpoolError):
            self.heads.status("worker.1", expected_tokenizer_digest=TOKENIZER)

    def test_missing_ancestor_blocks_advance(self):
        self.init()
        child = self.heads.advance("worker.1",
            expected_checkpoint_digest=self.genesis,
            expected_tokenizer_digest=TOKENIZER, consumed_tokens=1)
        (self.spool.checkpoints / self.genesis[:2] / self.genesis).unlink()
        with self.assertRaises(LongContextSpoolError):
            self.heads.advance("worker.1",
                expected_checkpoint_digest=child["checkpoint_digest"],
                expected_tokenizer_digest=TOKENIZER, consumed_tokens=1)

    def test_failed_replace_does_not_acknowledge_progress(self):
        self.init()
        with patch("skeleton.ai.model_runtime.long_context_progress.os.replace",
                   side_effect=OSError("disk denied")):
            with self.assertRaisesRegex(LongContextSpoolError, "ambiguous"):
                self.heads.advance("worker.1",
                    expected_checkpoint_digest=self.genesis,
                    expected_tokenizer_digest=TOKENIZER, consumed_tokens=1)
        self.assertEqual(self.heads.status("worker.1",
            expected_tokenizer_digest=TOKENIZER)["checkpoint_digest"], self.genesis)

    def test_orphan_recovery_preserves_committed_head(self):
        record = self.init()
        temp = self.spool.root / "heads" / (
            "." + record["stream_digest"] + "." + "a" * 16 + ".tmp")
        temp.write_bytes(b"partial")
        os.chmod(temp, 0o600)
        result = self.heads.recover_orphan_temps()
        self.assertEqual(result["removed"], 1)
        self.assertEqual(result["bytes_reclaimed"], 7)
        self.assertFalse(temp.exists())
        self.assertEqual(self.heads.status("worker.1",
            expected_tokenizer_digest=TOKENIZER)["checkpoint_digest"], self.genesis)

    def test_unknown_entries_deny_mutation_and_recovery(self):
        self.init()
        (self.spool.root / "heads" / "unexpected").write_bytes(b"x")
        with self.assertRaisesRegex(LongContextSpoolError, "untrusted"):
            self.heads.advance("worker.1",
                expected_checkpoint_digest=self.genesis,
                expected_tokenizer_digest=TOKENIZER, consumed_tokens=1)
        with self.assertRaisesRegex(LongContextSpoolError, "untrusted"):
            self.heads.recover_orphan_temps()

    def test_unknown_volume_telemetry_denies_initialization(self):
        with patch("skeleton.ai.model_runtime.long_context_progress._volume_available_bytes",
                   side_effect=LongContextSpoolError("telemetry unavailable")):
            with self.assertRaisesRegex(LongContextSpoolError, "telemetry"):
                self.init()

    def test_forked_process_cannot_reuse_inherited_spool(self):
        self.init()
        with patch("skeleton.ai.model_runtime.long_context_spool.os.getpid",
                   return_value=self.spool._owner_pid + 1):
            with self.assertRaisesRegex(LongContextSpoolError, "forked"):
                self.heads.status("worker.1", expected_tokenizer_digest=TOKENIZER)


if __name__ == "__main__":
    unittest.main()
