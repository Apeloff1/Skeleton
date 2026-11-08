"""Regression fixtures for bounded GGUF admission preflight (not inference)."""
import hashlib
import os
import struct
import tempfile
import unittest
from pathlib import Path

from skeleton.native.gguf_preflight import GGUFPreflightError, inspect_gguf


class GGUFPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "model.gguf"
        self.data = b"GGUF" + struct.pack("<IQQ", 3, 1, 0) + b"payload"
        self.path.write_bytes(self.data)
        self.digest = hashlib.sha256(self.data).hexdigest()

    def test_valid_header_and_exact_digest(self):
        result = inspect_gguf(self.path, expected_sha256=self.digest)
        self.assertEqual((result.version, result.tensor_count, result.metadata_count), (3, 1, 0))
        self.assertEqual(result.file_size, len(self.data))

    def test_digest_mismatch_denied(self):
        with self.assertRaisesRegex(GGUFPreflightError, "mismatch"):
            inspect_gguf(self.path, expected_sha256="0" * 64)

    def test_bad_magic_denied(self):
        self.path.write_bytes(b"BAD!" + self.data[4:])
        with self.assertRaisesRegex(GGUFPreflightError, "not a GGUF"):
            inspect_gguf(self.path, expected_sha256=hashlib.sha256(self.path.read_bytes()).hexdigest())

    def test_unbounded_counts_denied(self):
        self.path.write_bytes(b"GGUF" + struct.pack("<IQQ", 3, 2_000_000, 0))
        with self.assertRaisesRegex(GGUFPreflightError, "counts"):
            inspect_gguf(self.path, expected_sha256=hashlib.sha256(self.path.read_bytes()).hexdigest())

    def test_boolean_budget_denied(self):
        with self.assertRaisesRegex(GGUFPreflightError, "limits"):
            inspect_gguf(self.path, expected_sha256=self.digest, max_bytes=True)

    def test_size_budget_denied(self):
        with self.assertRaisesRegex(GGUFPreflightError, "size"):
            inspect_gguf(self.path, expected_sha256=self.digest, max_bytes=24)

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "platform lacks no-follow")
    def test_symlink_denied(self):
        alias = Path(self.temp.name) / "alias.gguf"
        alias.symlink_to(self.path)
        with self.assertRaises(GGUFPreflightError):
            inspect_gguf(alias, expected_sha256=self.digest)


if __name__ == "__main__":
    unittest.main()
