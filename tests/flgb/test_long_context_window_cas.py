"""Generation-fenced long-context token observation and CAS regression tests."""
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

TOKENIZER = sha256(b"window-cas-tokenizer").hexdigest()
SOURCE = sha256(b"window-cas-source").hexdigest()


@unittest.skipUnless(os.name == "posix", "POSIX pinned directory custody")
class TestGenerationFencedWindow(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.spool = LongContextSpool(Path(self.tmp.name) / "spool", disk_reserve_bytes=0)
        self.addCleanup(self.spool.close)
        self.heads = LongContextProgressHead(self.spool)
        self.genesis = self.spool.stage(TokenSequence(TOKENIZER, tuple(range(12)), SOURCE))
        self.initial = self.heads.initialize("stream.1", self.genesis,
            expected_tokenizer_digest=TOKENIZER)

    def observe(self, **kwargs):
        return self.heads.compare_window("stream.1",
            expected_checkpoint_digest=kwargs.get("checkpoint", self.genesis),
            expected_generation=kwargs.get("generation", 0),
            expected_tokenizer_digest=kwargs.get("tokenizer", TOKENIZER),
            max_tokens=kwargs.get("max_tokens", 4))

    def commit(self, observation, *, consumed=2, digest=None, **kwargs):
        return self.heads.advance_window("stream.1",
            expected_checkpoint_digest=kwargs.get("checkpoint", self.genesis),
            expected_generation=kwargs.get("generation", 0),
            expected_tokenizer_digest=kwargs.get("tokenizer", TOKENIZER),
            expected_window_digest=digest or observation["window"]["digest"],
            max_tokens=kwargs.get("max_tokens", 4),
            consumed_tokens=consumed)

    def test_exact_window_then_restart_and_resume(self):
        observed = self.observe()
        self.assertFalse(observed["is_execution_lease"])
        self.assertEqual(observed["window"]["token_ids"], [0, 1, 2, 3])
        result = self.commit(observed, consumed=3)
        self.assertEqual(result["generation"], 1)
        restarted = LongContextSpool(self.spool.root, disk_reserve_bytes=0)
        self.addCleanup(restarted.close)
        head = LongContextProgressHead(restarted)
        resumed = head.compare_window("stream.1",
            expected_checkpoint_digest=result["checkpoint_digest"],
            expected_generation=1, expected_tokenizer_digest=TOKENIZER, max_tokens=4)
        self.assertEqual(resumed["window"]["token_ids"], [3, 4, 5, 6])

    def test_stale_observation_never_commits_twice(self):
        observed = self.observe()
        self.commit(observed)
        with self.assertRaisesRegex(LongContextSpoolError, "stale"):
            self.commit(observed)
        with self.assertRaisesRegex(LongContextSpoolError, "stale"):
            self.observe()
        self.assertEqual(self.heads.status("stream.1",
            expected_tokenizer_digest=TOKENIZER)["generation"], 1)

    def test_forged_digest_and_wrong_window_size_denied(self):
        observed = self.observe()
        for digest, max_tokens in ((SOURCE, 4), (observed["window"]["digest"], 3)):
            with self.subTest(digest=digest, max_tokens=max_tokens):
                with self.assertRaisesRegex(LongContextSpoolError, "window digest"):
                    self.commit(observed, digest=digest, max_tokens=max_tokens)
        self.assertEqual(self.observe()["window"]["token_ids"], [0, 1, 2, 3])

    def test_invalid_generation_and_consumption_denied(self):
        observed = self.observe()
        for generation in (True, -1, 2**63, "0", 1):
            with self.subTest(generation=generation), self.assertRaises(LongContextSpoolError):
                self.commit(observed, generation=generation)
        for count in (0, -1, True, 5, 2**40):
            with self.subTest(count=count), self.assertRaises(LongContextSpoolError):
                self.commit(observed, consumed=count)
        for size in (0, True, 65537):
            with self.subTest(size=size), self.assertRaises(LongContextSpoolError):
                self.observe(max_tokens=size)

    def test_concurrent_exact_window_commit_is_single_winner(self):
        observed = self.observe()
        def attempt(_):
            try:
                return self.commit(observed)
            except LongContextSpoolError as exc:
                return str(exc)
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(attempt, (0, 1)))
        self.assertEqual(sum(isinstance(value, dict) for value in outcomes), 1)
        self.assertTrue(any(isinstance(value, str) and "stale" in value for value in outcomes))

    def test_missing_ancestor_blocks_observation_and_commit(self):
        observed = self.observe()
        (self.spool.checkpoints / self.genesis[:2] / self.genesis).unlink()
        with self.assertRaises(LongContextSpoolError):
            self.observe()
        with self.assertRaises(LongContextSpoolError):
            self.commit(observed)

    def test_failed_publication_never_acknowledges_progress(self):
        observed = self.observe()
        with patch("skeleton.ai.model_runtime.long_context_progress.os.replace",
                   side_effect=OSError("disk full")):
            with self.assertRaisesRegex(LongContextSpoolError, "ambiguous"):
                self.commit(observed)
        self.assertEqual(self.observe()["generation"], 0)

    def test_completed_stream_is_not_reexecuted(self):
        observed = self.observe(max_tokens=12)
        done = self.commit(observed, consumed=12, max_tokens=12)
        exhausted = self.observe(checkpoint=done["checkpoint_digest"], generation=1)
        self.assertIsNone(exhausted["window"])
        with self.assertRaisesRegex(LongContextSpoolError, "window digest"):
            self.heads.advance_window("stream.1",
                expected_checkpoint_digest=done["checkpoint_digest"],
                expected_generation=1, expected_tokenizer_digest=TOKENIZER,
                expected_window_digest=observed["window"]["digest"],
                max_tokens=4, consumed_tokens=1)

    def test_wrong_tokenizer_and_fork_are_denied(self):
        with self.assertRaises(LongContextSpoolError):
            self.observe(tokenizer=SOURCE)
        with patch("skeleton.ai.model_runtime.long_context_spool.os.getpid",
                   return_value=self.spool._owner_pid + 1):
            with self.assertRaisesRegex(LongContextSpoolError, "forked"):
                self.observe()


if __name__ == "__main__":
    unittest.main()
