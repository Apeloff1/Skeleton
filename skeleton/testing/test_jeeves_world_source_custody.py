"""Filesystem custody regression for canonical Jeeves source reads.

Run: python -m unittest skeleton.testing.test_jeeves_world_source_custody -v
"""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from skeleton.jeeves.worlds.world_canon import CanonError, WorldStore


@unittest.skipUnless(hasattr(os, "O_NOFOLLOW") and os.open in os.supports_dir_fd,
                     "descriptor anchored filesystem required")
class WorldSourceCustodyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = WorldStore(self.tmp.name)
        self.root = Path(self.tmp.name)

    def read(self, name="original.json"):
        fd = self.store._directory()
        try:
            return self.store._read(fd, name)
        finally:
            os.close(fd)

    def test_regular_source_read(self):
        (self.root / "original.json").write_bytes(b'{"valid":true}')
        self.assertEqual(self.read(), b'{"valid":true}')

    def test_hardlinked_source_rejected_without_mutation(self):
        external = self.root / "external"
        external.write_bytes(b"private")
        os.link(external, self.root / "original.json")
        with self.assertRaises(CanonError) as raised:
            self.read()
        self.assertEqual(raised.exception.code, "unsafe_source_file")
        self.assertEqual(external.read_bytes(), b"private")

    def test_symlink_source_rejected(self):
        (self.root / "external").write_bytes(b"private")
        (self.root / "original.json").symlink_to("external")
        with self.assertRaises(OSError):
            self.read()

    def test_symlinked_ancestor_cannot_redirect_private_world_creation(self):
        actual = self.root / "actual-parent"
        actual.mkdir()
        linked = self.root / "linked-parent"
        linked.symlink_to(actual, target_is_directory=True)
        with self.assertRaises(CanonError):
            WorldStore(linked / "world-store")
        self.assertFalse((actual / "world-store").exists())

    def test_same_size_mutation_with_restored_mtime_is_rejected(self):
        import time
        source = self.root / "original.json"
        source.write_bytes(b"original")
        before = source.stat()
        real_stat = os.stat
        tampered = False

        def rewrite(path, *args, **kwargs):
            nonlocal tampered
            if path == "original.json" and not tampered:
                tampered = True
                # Restore mtime deliberately; ctime remains non-replayable.
                time.sleep(0.003)
                with source.open("r+b") as stream:
                    stream.write(b"altered!")
                os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns))
            return real_stat(path, *args, **kwargs)

        with patch("skeleton.jeeves.worlds.world_canon.os.stat", side_effect=rewrite):
            with self.assertRaises(CanonError) as raised:
                self.read()
        self.assertEqual(raised.exception.code, "source_replaced_during_read")
        self.assertTrue(tampered)

    def test_replacement_between_open_and_validation_rejected(self):
        source = self.root / "original.json"
        source.write_bytes(b"old")
        real_stat = os.stat
        replaced = False

        def swap(path, *args, **kwargs):
            nonlocal replaced
            if path == "original.json" and not replaced:
                replaced = True
                source.replace(self.root / "old.json")
                source.write_bytes(b"new")
            return real_stat(path, *args, **kwargs)

        with patch("skeleton.jeeves.worlds.world_canon.os.stat", side_effect=swap):
            with self.assertRaises(CanonError) as raised:
                self.read()
        self.assertEqual(raised.exception.code, "source_replaced_during_read")
        self.assertEqual(source.read_bytes(), b"new")


if __name__ == "__main__":
    unittest.main()
