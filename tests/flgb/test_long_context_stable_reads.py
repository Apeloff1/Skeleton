"""POSIX immutable spool reads must reject inode and content TOCTOU races."""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from skeleton.ai.model_runtime.flgb_model_runtime import TokenSequence
from skeleton.ai.model_runtime.long_context_spool import (
    LongContextSpool, LongContextSpoolError, _read_stable_named_fd,
)

TOKENIZER = sha256(b"stable-read-tokenizer").hexdigest()
SOURCE = sha256(b"stable-read-source").hexdigest()


@unittest.skipUnless(os.name == "posix", "descriptor-relative POSIX custody")
class TestImmutableReadIdentity(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.spool = LongContextSpool(Path(self.temp.name) / "spool",
                                      disk_reserve_bytes=0)
        self.addCleanup(self.spool.close)
        self.sequence = TokenSequence(TOKENIZER, tuple(range(16)), SOURCE)
        self.checkpoint = self.spool.stage(self.sequence)
        self.record, self.loaded = self.spool.load(
            self.checkpoint, expected_tokenizer_digest=TOKENIZER)
        self.assertEqual(self.loaded, self.sequence)
        self.object_path = self.spool._path("object", self.record.object_digest)

    def test_stable_checkpoint_and_object_round_trip(self):
        checkpoint, sequence = self.spool.load(
            self.checkpoint, expected_tokenizer_digest=TOKENIZER)
        self.assertEqual(checkpoint, self.record)
        self.assertEqual(sequence, self.sequence)
        self.assertEqual(self.spool.stage(self.sequence), self.checkpoint)

    def test_invalid_limits_fail_before_open(self):
        bucket = self.spool._open_bucket("object", self.record.object_digest)
        try:
            for limit in (True, -1, 1.5, "100"):
                with self.subTest(limit=limit), self.assertRaisesRegex(
                        LongContextSpoolError, "limit"):
                    _read_stable_named_fd(bucket, self.record.object_digest,
                                          limit=limit)
            with self.assertRaisesRegex(LongContextSpoolError, "byte budget"):
                _read_stable_named_fd(bucket, self.record.object_digest, limit=1)
        finally:
            os.close(bucket)

    def test_replaced_name_with_identical_bytes_is_not_a_valid_read(self):
        original_stat = os.stat
        raw = self.object_path.read_bytes()
        name = self.record.object_digest
        swapped = False

        def replace_before_named_check(path, *args, **kwargs):
            nonlocal swapped
            if not swapped and path == name and kwargs.get("dir_fd") is not None:
                swapped = True
                directory = kwargs["dir_fd"]
                os.unlink(name, dir_fd=directory)
                fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                             0o600, dir_fd=directory)
                try:
                    os.write(fd, raw)
                finally:
                    os.close(fd)
            return original_stat(path, *args, **kwargs)

        with patch("skeleton.ai.model_runtime.long_context_spool.os.stat",
                   side_effect=replace_before_named_check):
            with self.assertRaisesRegex(LongContextSpoolError, "changed during read"):
                self.spool.load(self.checkpoint,
                                expected_tokenizer_digest=TOKENIZER)
        self.assertTrue(swapped)

    def test_in_place_mutation_after_read_is_rejected(self):
        original_stat = os.stat
        name = self.record.object_digest
        mutated = False

        def mutate_before_named_check(path, *args, **kwargs):
            nonlocal mutated
            if not mutated and path == name and kwargs.get("dir_fd") is not None:
                mutated = True
                fd = os.open(name, os.O_WRONLY | os.O_NOFOLLOW,
                             dir_fd=kwargs["dir_fd"])
                try:
                    os.pwrite(fd, b"X", 0)
                    os.fsync(fd)
                    # Force a deterministic metadata transition even on
                    # coarse-resolution filesystems and very fast runners.
                    before = os.fstat(fd)
                    os.utime(name, ns=(before.st_atime_ns,
                                       before.st_mtime_ns + 2_000_000_000),
                             dir_fd=kwargs["dir_fd"], follow_symlinks=False)
                finally:
                    os.close(fd)
            return original_stat(path, *args, **kwargs)

        with patch("skeleton.ai.model_runtime.long_context_spool.os.stat",
                   side_effect=mutate_before_named_check):
            with self.assertRaisesRegex(LongContextSpoolError, "changed during read"):
                self.spool.load(self.checkpoint,
                                expected_tokenizer_digest=TOKENIZER)
        self.assertTrue(mutated)

    def test_unlinked_name_after_read_is_rejected(self):
        original_stat = os.stat
        name = self.record.object_digest
        removed = False

        def unlink_before_named_check(path, *args, **kwargs):
            nonlocal removed
            if not removed and path == name and kwargs.get("dir_fd") is not None:
                removed = True
                os.unlink(name, dir_fd=kwargs["dir_fd"])
            return original_stat(path, *args, **kwargs)

        with patch("skeleton.ai.model_runtime.long_context_spool.os.stat",
                   side_effect=unlink_before_named_check):
            with self.assertRaisesRegex(LongContextSpoolError, "changed during read"):
                self.spool.load(self.checkpoint,
                                expected_tokenizer_digest=TOKENIZER)
        self.assertTrue(removed)

    def test_existing_object_collision_detects_postread_name_swap(self):
        original_stat = os.stat
        name = self.record.object_digest
        raw = self.object_path.read_bytes()
        checks = 0

        def replace_on_final_check(path, *args, **kwargs):
            nonlocal checks
            if path == name and kwargs.get("dir_fd") is not None:
                checks += 1
                if checks == 2:
                    directory = kwargs["dir_fd"]
                    os.unlink(name, dir_fd=directory)
                    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                                 0o600, dir_fd=directory)
                    try:
                        os.write(fd, raw)
                    finally:
                        os.close(fd)
            return original_stat(path, *args, **kwargs)

        with patch("skeleton.ai.model_runtime.long_context_spool.os.stat",
                   side_effect=replace_on_final_check):
            with self.assertRaisesRegex(LongContextSpoolError,
                                        "changed during read"):
                self.spool.stage(self.sequence)
        self.assertEqual(checks, 2)

    def test_changed_permissions_during_read_are_denied(self):
        original_stat = os.stat
        name = self.record.object_digest
        changed = False

        def chmod_before_named_check(path, *args, **kwargs):
            nonlocal changed
            if not changed and path == name and kwargs.get("dir_fd") is not None:
                changed = True
                os.chmod(name, 0o644, dir_fd=kwargs["dir_fd"],
                         follow_symlinks=False)
            return original_stat(path, *args, **kwargs)

        with patch("skeleton.ai.model_runtime.long_context_spool.os.stat",
                   side_effect=chmod_before_named_check):
            with self.assertRaisesRegex(LongContextSpoolError,
                                        "changed during read"):
                self.spool.load(self.checkpoint,
                                expected_tokenizer_digest=TOKENIZER)
        self.assertTrue(changed)

    def test_immutable_restage_rejects_corrupted_existing_object(self):
        fd = os.open(self.object_path, os.O_WRONLY | os.O_NOFOLLOW)
        try:
            os.pwrite(fd, b"X", 0)
            os.fsync(fd)
        finally:
            os.close(fd)
        with self.assertRaises(LongContextSpoolError):
            self.spool.stage(self.sequence)


if __name__ == "__main__":
    unittest.main()
