"""Whole-root POSIX long-context recovery audit: strict bounded, payload-free evidence."""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.ai.model_runtime.flgb_model_runtime import TokenSequence
from skeleton.ai.model_runtime.long_context_spool import LongContextSpool, LongContextSpoolError
from skeleton.ai.model_runtime.long_context_progress import LongContextProgressHead

TOKENIZER = sha256(b"inventory-tokenizer").hexdigest()
SOURCE = sha256(b"inventory-source").hexdigest()
OTHER = sha256(b"other-tokenizer").hexdigest()


@unittest.skipUnless(os.name == "posix", "POSIX descriptor-relative audit")
class TestHeadInventoryAudit(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.spool = LongContextSpool(Path(self.tmp.name) / "spool", disk_reserve_bytes=0)
        self.addCleanup(self.spool.close)
        self.heads = LongContextProgressHead(self.spool)
        self.genesis = self.spool.stage(TokenSequence(TOKENIZER, tuple(range(12)), SOURCE))

    def initialize(self, name="alpha"):
        return self.heads.initialize(name, self.genesis,
            expected_tokenizer_digest=TOKENIZER)

    def audit(self, **kwargs):
        return self.heads.audit_inventory(
            expected_tokenizer_digest=kwargs.get("tokenizer", TOKENIZER),
            max_heads=kwargs.get("max_heads", 64),
            max_checkpoints=kwargs.get("max_checkpoints", 4096))

    def test_empty_inventory_and_two_committed_heads(self):
        empty = self.audit()
        self.assertEqual(empty["heads_verified"], 0)
        self.assertTrue(empty["complete"])
        self.assertFalse(empty["token_payloads_returned"])
        self.initialize("alpha")
        self.initialize("beta")
        evidence = self.audit()
        self.assertEqual(evidence["heads_verified"], 2)
        self.assertEqual(len(evidence["inventory_digest"]), 64)
        self.assertFalse(evidence["trusted_publisher_attested"])
        self.assertFalse(evidence["external_replay_fence_attested"])
        self.assertNotIn("token_ids", str(evidence))
        self.assertNotIn("stream_digest", evidence)
        self.assertNotEqual(evidence["inventory_digest"], empty["inventory_digest"])

    def test_restart_produces_same_aggregate_evidence(self):
        self.initialize()
        expected = self.audit()
        restarted = LongContextSpool(self.spool.root, disk_reserve_bytes=0)
        self.addCleanup(restarted.close)
        observed = LongContextProgressHead(restarted).audit_inventory(
            expected_tokenizer_digest=TOKENIZER)
        self.assertEqual(observed, expected)

    def test_committed_progress_changes_aggregate_digest(self):
        self.initialize()
        before = self.audit()
        self.heads.advance("alpha", expected_checkpoint_digest=self.genesis,
            expected_tokenizer_digest=TOKENIZER, consumed_tokens=1)
        after = self.audit()
        self.assertEqual(after["heads_verified"], 1)
        self.assertNotEqual(before["inventory_digest"], after["inventory_digest"])

    def test_wrong_tokenizer_rejects_whole_root(self):
        self.initialize()
        with self.assertRaisesRegex(LongContextSpoolError, "identity"):
            self.audit(tokenizer=OTHER)

    def test_invalid_and_excessive_bounds_rejected(self):
        self.initialize()
        for bound in (0, -1, True, 4097):
            with self.subTest(bound=bound), self.assertRaises(LongContextSpoolError):
                self.audit(max_heads=bound)
        with self.assertRaisesRegex(LongContextSpoolError, "count bound"):
            self._two_heads_audit()
        with self.assertRaisesRegex(LongContextSpoolError, "work bound"):
            self.audit(max_heads=4096, max_checkpoints=4096)

    def _two_heads_audit(self):
        self.initialize("beta")
        return self.audit(max_heads=1)

    def test_missing_checkpoint_fails_entire_inventory(self):
        self.initialize()
        (self.spool.checkpoints / self.genesis[:2] / self.genesis).unlink()
        with self.assertRaises(LongContextSpoolError):
            self.audit()

    def test_symlink_and_unknown_entry_fail_closed(self):
        self.initialize()
        heads_dir = self.spool.root / "heads"
        bad = heads_dir / "unexpected"
        bad.write_bytes(b"x")
        with self.assertRaisesRegex(LongContextSpoolError, "untrusted"):
            self.audit()
        bad.unlink()
        bad.symlink_to(self.spool.root / "missing")
        with self.assertRaisesRegex(LongContextSpoolError, "untrusted"):
            self.audit()

    def test_orphan_temps_observed_but_not_deleted(self):
        record = self.initialize()
        temp = self.spool.root / "heads" / (
            "." + record["stream_digest"] + "." + "f" * 16 + ".tmp")
        temp.write_bytes(b"orphan")
        os.chmod(temp, 0o600)
        result = self.audit()
        self.assertEqual(result["orphan_temps_observed"], 1)
        self.assertTrue(temp.exists())

    def test_forked_process_rejected(self):
        from unittest.mock import patch
        self.initialize()
        with patch("skeleton.ai.model_runtime.long_context_spool.os.getpid",
                   return_value=self.spool._owner_pid + 1):
            with self.assertRaisesRegex(LongContextSpoolError, "forked"):
                self.audit()


if __name__ == "__main__":
    unittest.main()
