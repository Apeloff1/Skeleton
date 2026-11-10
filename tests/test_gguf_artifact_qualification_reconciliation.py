"""GGUF artifact custody: no simulated inference or partial-file digest acceptance.

This is source-level acceptance, not live native GGUF loader, OS installer or
inference-provider certification.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import struct
import tempfile
import unittest

from skeleton.local_ai.model_loader import ModelLoader


class GuardedGGUFArtifactTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "model.gguf"
        self.data = b"GGUF" + struct.pack("<IQQ", 3, 1, 1) + b"original-test-model"
        self.path.write_bytes(self.data)

    def qualify(self, *, data=None, path=None, sha=None):
        if data is not None:
            self.path.write_bytes(data)
        target = path or self.path
        expected = sha or hashlib.sha256(self.data).hexdigest()
        loader = ModelLoader(str(target), expected_sha256=expected)
        return loader, loader.load("c" * 32, license_accepted=True)

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "secure no-follow open required")
    def test_full_header_and_full_digest_never_claim_model_loaded(self):
        model, receipt = self.qualify()
        self.assertEqual(receipt["status"], "artifact_verified_not_loaded")
        self.assertEqual(receipt["bytes"], len(self.data))
        self.assertEqual(receipt["digest"], hashlib.sha256(self.data).hexdigest())
        self.assertFalse(model.loaded)
        self.assertFalse(model.verify(receipt["digest"]))

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "secure no-follow open required")
    def test_tail_modification_breaks_full_digest(self):
        modified = self.data + b"tampered-after-header"
        with self.assertRaisesRegex(ValueError, "mismatch"):
            self.qualify(data=modified)

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "secure no-follow open required")
    def test_invalid_magic_version_and_counts_fail_closed(self):
        invalid = [
            b"GGUF", b"NOPE" + self.data[4:],
            b"GGUF" + struct.pack("<IQQ", 1, 1, 1),
            b"GGUF" + struct.pack("<IQQ", 3, 0, 1),
            b"GGUF" + struct.pack("<IQQ", 3, 1, 0),
            b"GGUF" + struct.pack("<IQQ", 3, 100000, 1),
        ]
        for payload in invalid:
            with self.subTest(size=len(payload)):
                with self.assertRaises(ValueError):
                    self.qualify(data=payload, sha=hashlib.sha256(payload).hexdigest())

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "secure no-follow open required")
    def test_single_link_and_symlink_custody(self):
        alias = self.path.with_suffix(".alias")
        os.link(self.path, alias)
        with self.assertRaisesRegex(ValueError, "non-hardlinked"):
            self.qualify()
        alias.unlink()
        alias.symlink_to(self.path)
        with self.assertRaises(OSError):
            self.qualify(path=alias)

    def test_unconfigured_loader_remains_not_loaded(self):
        loader = ModelLoader()
        with self.assertRaises(FileNotFoundError):
            loader.load("c" * 32, license_accepted=True)
        self.assertFalse(loader.loaded)


if __name__ == "__main__":
    unittest.main()
