"""POSIX fd-anchored evidence reads resist traversal, symlink and oversize."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from skeleton.ai.runtime.operational_ai.guarded_request.workspace import (
    read_private_leaf, require_leaf,
)
from skeleton.ai.runtime.operational_ai.guarded_request.errors import GateDenied


@unittest.skipUnless(os.name == "posix" and hasattr(os, "O_NOFOLLOW"), "POSIX descriptor custody")
class TestPrivateWorkspace(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        os.chmod(self.root, 0o700)
        self.fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)

    def tearDown(self):
        os.close(self.fd)
        self.tmp.cleanup()

    def add_file(self, name, data):
        path = self.root / name
        with open(path, "xb") as output:
            output.write(data)
        os.chmod(path, 0o600)
        return path

    def test_exact_bounded_bytes(self):
        self.add_file("model.json", b"verified")
        self.assertEqual(read_private_leaf(self.fd, "model.json"), b"verified")

    def test_traversal_and_subdirectories(self):
        for name in ("../secret", "/etc/passwd", ".hidden", "a/b"):
            with self.subTest(name=name), self.assertRaises(GateDenied):
                require_leaf(name)

    def test_symlink_refused(self):
        self.add_file("target.bin", b"real")
        (self.root / "alias.bin").symlink_to("target.bin")
        with self.assertRaises(GateDenied):
            read_private_leaf(self.fd, "alias.bin")

    def test_hardlink_refused(self):
        original = self.add_file("source.bin", b"real")
        os.link(original, self.root / "copy.bin")
        with self.assertRaises(GateDenied):
            read_private_leaf(self.fd, "copy.bin")

    def test_oversize_refused(self):
        self.add_file("oversize.bin", b"x" * 101)
        with self.assertRaises(GateDenied):
            read_private_leaf(self.fd, "oversize.bin", max_bytes=100)

    def test_public_root_refused(self):
        self.add_file("trusted.bin", b"v")
        os.chmod(self.root, 0o755)
        with self.assertRaises(GateDenied):
            read_private_leaf(self.fd, "trusted.bin")


if __name__ == "__main__":
    unittest.main()
