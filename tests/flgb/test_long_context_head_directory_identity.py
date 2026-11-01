"""Descriptor/name fencing for durable head lock and directory custody."""
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
    LongContextSpool, LongContextSpoolError,
)

TOKENIZER = sha256(b"head-name-fence-tokenizer").hexdigest()
SOURCE = sha256(b"head-name-fence-source").hexdigest()


@unittest.skipUnless(os.name == "posix", "POSIX pinned directory custody")
class TestHeadDirectoryNameFencing(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.spool = LongContextSpool(Path(self.temp.name) / "spool",
                                      disk_reserve_bytes=0)
        self.addCleanup(self.spool.close)
        self.heads = LongContextProgressHead(self.spool)
        self.checkpoint = self.spool.stage(
            TokenSequence(TOKENIZER, tuple(range(8)), SOURCE))
        self.heads.initialize("stream.1", self.checkpoint,
                              expected_tokenizer_digest=TOKENIZER)

    def test_stable_head_status_and_advance_still_work(self):
        first = self.heads.status("stream.1",
                                  expected_tokenizer_digest=TOKENIZER)
        self.assertEqual(first["generation"], 0)
        advanced = self.heads.advance("stream.1",
            expected_checkpoint_digest=self.checkpoint,
            expected_tokenizer_digest=TOKENIZER, consumed_tokens=1)
        self.assertEqual(advanced["generation"], 1)

    def test_directory_swap_between_open_and_use_is_denied(self):
        original_open = os.open
        root = self.spool._root_fd
        swapped = False

        def swap_after_open(path, flags, *args, **kwargs):
            nonlocal swapped
            fd = original_open(path, flags, *args, **kwargs)
            if path == "heads" and kwargs.get("dir_fd") == root and not swapped:
                swapped = True
                os.rename("heads", "heads.detached",
                          src_dir_fd=root, dst_dir_fd=root)
                os.mkdir("heads", 0o700, dir_fd=root)
            return fd

        with patch("skeleton.ai.model_runtime.long_context_progress.os.open",
                   side_effect=swap_after_open):
            with self.assertRaisesRegex(LongContextSpoolError,
                                        "head directory replaced"):
                self.heads.status("stream.1",
                                  expected_tokenizer_digest=TOKENIZER)
        self.assertTrue(swapped)

    def test_directory_swap_while_lock_held_never_acknowledges(self):
        root = self.spool._root_fd
        with self.assertRaisesRegex(LongContextSpoolError,
                                    "head directory replaced"):
            with self.heads._locked():
                os.rename("heads", "heads.detached",
                          src_dir_fd=root, dst_dir_fd=root)
                os.mkdir("heads", 0o700, dir_fd=root)

    def test_lock_inode_replacement_while_held_never_acknowledges(self):
        root = self.spool._root_fd
        with self.assertRaisesRegex(LongContextSpoolError,
                                    "head lock replaced"):
            with self.heads._locked():
                os.unlink(".heads.lock", dir_fd=root)
                new_fd = os.open(".heads.lock",
                                 os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                                 0o600, dir_fd=root)
                os.close(new_fd)

    def test_head_directory_symlink_is_denied(self):
        root = self.spool._root_fd
        os.rename("heads", "heads.detached",
                  src_dir_fd=root, dst_dir_fd=root)
        os.symlink("heads.detached", "heads", dir_fd=root)
        with self.assertRaises(LongContextSpoolError):
            self.heads.status("stream.1",
                              expected_tokenizer_digest=TOKENIZER)


if __name__ == "__main__":
    unittest.main()
