"""Regression contracts for pinned long-context root and selected-source ancestry.

A POSIX descriptor remains usable after its directory is renamed. A durable
acknowledgement must nevertheless reject a root that is no longer reachable
at the operator-authorized path. These tests do not claim hostile same-UID
filesystem transaction isolation or Windows device qualification.
"""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from skeleton.ai.model_runtime.flgb_model_runtime import TokenSequence
from skeleton.ai.model_runtime.long_context_progress import LongContextProgressHead
from skeleton.ai.model_runtime.long_context_spool import (
    LongContextSpool, LongContextSpoolError, read_selected_sequence,
)
from skeleton.ai.model_runtime.tokenization import serialize_token_sequence

TOKENIZER = sha256(b"root-guard tokenizer").hexdigest()
SOURCE = sha256(b"root-guard source").hexdigest()


@unittest.skipUnless(os.name == "posix", "descriptor-pinned root requires POSIX")
class TestLongContextRootGuard(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.anchor = Path(self.directory.name) / "anchor"
        self.anchor.mkdir(mode=0o700)
        self.root = self.anchor / "spool"
        self.spool = LongContextSpool(self.root, disk_reserve_bytes=0)
        self.addCleanup(self.spool.close)
        self.sequence = TokenSequence(TOKENIZER, tuple(range(12)), SOURCE)

    def replace_root(self) -> Path:
        moved = self.anchor / "old-spool"
        self.root.rename(moved)
        self.root.mkdir(mode=0o700)
        return moved

    def test_replaced_root_rejects_capacity_and_publication(self) -> None:
        self.replace_root()
        with self.assertRaisesRegex(LongContextSpoolError, "root path replaced"):
            self.spool.capacity_snapshot()
        with self.assertRaisesRegex(LongContextSpoolError, "root path replaced"):
            self.spool.stage(self.sequence)
        self.assertFalse((self.root / "objects").exists())

    def test_missing_root_path_fails_closed(self) -> None:
        moved = self.anchor / "renamed"
        self.root.rename(moved)
        with self.assertRaisesRegex(LongContextSpoolError, "root path unavailable"):
            self.spool.capacity_snapshot()
        with self.assertRaisesRegex(LongContextSpoolError, "root path unavailable"):
            self.spool.stage(self.sequence)

    def test_root_permission_drift_fails_closed(self) -> None:
        self.root.chmod(0o750)
        with self.assertRaisesRegex(LongContextSpoolError, "root path replaced or insecure"):
            self.spool.capacity_snapshot()

    def test_parent_directory_replacement_fails_closed(self) -> None:
        old_anchor = Path(self.directory.name) / "old-anchor"
        self.anchor.rename(old_anchor)
        self.anchor.mkdir(mode=0o700)
        self.root.mkdir(mode=0o700)
        with self.assertRaisesRegex(LongContextSpoolError, "root path replaced"):
            self.spool.stage(self.sequence)

    def test_read_rejects_root_replacement_after_content_was_read(self) -> None:
        digest = self.spool.stage(self.sequence)
        import skeleton.ai.model_runtime.long_context_spool as module
        original = module._read_stable_named_fd
        triggered = False

        def swap_after_read(*args, **kwargs):
            nonlocal triggered
            raw = original(*args, **kwargs)
            if not triggered:
                triggered = True
                self.replace_root()
            return raw

        with patch.object(module, "_read_stable_named_fd", side_effect=swap_after_read):
            with self.assertRaisesRegex(LongContextSpoolError, "root path replaced"):
                self.spool.load(digest, expected_tokenizer_digest=TOKENIZER)
        self.assertTrue(triggered)

    def test_head_status_rejects_root_replacement_before_ack(self) -> None:
        digest = self.spool.stage(self.sequence)
        head = LongContextProgressHead(self.spool)
        head.initialize("stream", digest, expected_tokenizer_digest=TOKENIZER)
        original = LongContextProgressHead._read
        triggered = False

        def swap_after_head_read(directory, name):
            nonlocal triggered
            record = original(directory, name)
            if not triggered:
                triggered = True
                self.replace_root()
            return record

        with patch.object(LongContextProgressHead, "_read",
                          staticmethod(swap_after_head_read)):
            with self.assertRaisesRegex(LongContextSpoolError, "root path replaced"):
                head.status("stream", expected_tokenizer_digest=TOKENIZER)
        self.assertTrue(triggered)

    def test_selected_sequence_rejects_replaced_ancestor(self) -> None:
        selected = self.anchor / "source" / "sequence.json"
        selected.parent.mkdir(mode=0o700)
        raw = serialize_token_sequence(self.sequence)
        selected.write_bytes(raw)
        import skeleton.ai.model_runtime.long_context_spool as module
        original = module._read_stable_selected_fd
        triggered = False

        def replace_parent_after_read(*args, **kwargs):
            nonlocal triggered
            result = original(*args, **kwargs)
            if not triggered:
                triggered = True
                selected.parent.rename(self.anchor / "old-source")
                selected.parent.mkdir(mode=0o700)
                selected.write_bytes(b"replacement")
            return result

        with patch.object(module, "_read_stable_selected_fd",
                          side_effect=replace_parent_after_read):
            with self.assertRaisesRegex(LongContextSpoolError, "ancestor replaced"):
                read_selected_sequence(selected, limit=len(raw) + 16)
        self.assertTrue(triggered)

    def test_read_only_missing_digest_does_not_create_bucket(self) -> None:
        absent = "ab" * 32
        bucket = self.spool.checkpoints / absent[:2]
        self.assertFalse(bucket.exists())
        with self.assertRaises(LongContextSpoolError):
            self.spool.load(absent, expected_tokenizer_digest=TOKENIZER)
        self.assertFalse(bucket.exists())

    def test_recovery_missing_digest_does_not_create_bucket(self) -> None:
        absent = "cd" * 32
        bucket = self.spool.objects / absent[:2]
        self.assertFalse(bucket.exists())
        with self.assertRaises(LongContextSpoolError):
            self.spool.recover_abandoned_temps(kind="object", digest=absent)
        self.assertFalse(bucket.exists())

    def test_read_rejects_replaced_bucket_after_verified_bytes(self) -> None:
        digest = self.spool.stage(self.sequence)
        bucket = self.spool.checkpoints / digest[:2]
        import skeleton.ai.model_runtime.long_context_spool as module
        original = module._read_stable_named_fd
        triggered = False

        def replace_bucket_after_read(*args, **kwargs):
            nonlocal triggered
            raw = original(*args, **kwargs)
            if not triggered:
                triggered = True
                bucket.rename(bucket.with_name("moved-" + digest[:2]))
                bucket.mkdir(mode=0o700)
            return raw

        with patch.object(module, "_read_stable_named_fd",
                          side_effect=replace_bucket_after_read):
            with self.assertRaisesRegex(LongContextSpoolError, "bucket path replaced"):
                self.spool.load(digest, expected_tokenizer_digest=TOKENIZER)
        self.assertTrue(triggered)

    def test_publication_rejects_bucket_replacement_before_ack(self) -> None:
        import skeleton.ai.model_runtime.long_context_spool as module
        original = LongContextSpool._verify_bucket_path
        triggered = False

        def replace_bucket_before_verify(spool, kind, digest, bucket_fd):
            nonlocal triggered
            if not triggered:
                triggered = True
                path = (spool.objects if kind == "object" else spool.checkpoints) / digest[:2]
                path.rename(path.with_name("moved-" + digest[:2]))
                path.mkdir(mode=0o700)
            return original(spool, kind, digest, bucket_fd)

        with patch.object(LongContextSpool, "_verify_bucket_path",
                          replace_bucket_before_verify):
            with self.assertRaisesRegex(LongContextSpoolError, "bucket path replaced"):
                self.spool.stage(self.sequence)
        self.assertTrue(triggered)

    def test_unchanged_root_and_selected_source_remain_usable(self) -> None:
        digest = self.spool.stage(self.sequence)
        receipt, loaded = self.spool.load(digest, expected_tokenizer_digest=TOKENIZER)
        self.assertEqual(loaded, self.sequence)
        self.assertEqual(receipt.cursor, 0)
        self.assertEqual(self.spool.capacity_snapshot(requested_bytes=1)["state"],
                         "observed_available")
        selected = self.anchor / "sequence.json"
        raw = serialize_token_sequence(self.sequence)
        selected.write_bytes(raw)
        self.assertEqual(read_selected_sequence(selected, limit=len(raw)), raw)


if __name__ == "__main__":
    unittest.main()
