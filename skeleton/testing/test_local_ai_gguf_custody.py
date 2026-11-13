"""POSIX descriptor-custody attacks on GGUF artifact qualification.

A verified file is not a loaded model, and neither a path alias nor a
changed inode may publish a success receipt. No actual model is inferred.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
import struct
import tempfile
import unittest
from unittest.mock import patch

from skeleton.local_ai import model_loader
from skeleton.local_ai.model_loader import ModelLoader


_CAS = "test-custody-admission-cas-v1"
_VALID = b"GGUF" + struct.pack("<IQQ", 3, 1, 1) + b"not-real-weights-private-fixture"


@unittest.skipUnless(os.name == "posix", "Descriptor-anchored GGUF custody is POSIX-only")
class TestLocalAIGGUFCustody(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="gguf-safe-custody-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.model = self.root / "weights.gguf"
        self.model.write_bytes(_VALID)

    def loader(self, path: Path | None = None, digest: str | None = None) -> ModelLoader:
        return ModelLoader(
            str(path or self.model),
            expected_sha256=digest or hashlib.sha256(_VALID).hexdigest(),
            license_accepted=True,
            max_bytes=1024 * 1024,
        )

    def test_successful_file_custody_never_claims_model_loaded(self):
        loader = self.loader()
        result = loader.load(_CAS)
        self.assertEqual(result["status"], "artifact_verified_not_loaded")
        self.assertEqual(result["digest"], hashlib.sha256(_VALID).hexdigest())
        self.assertFalse(loader.loaded)
        self.assertFalse(loader.verify(result["digest"]))

    def test_symlinked_leaf_denied(self):
        alias = self.root / "alias.gguf"
        alias.symlink_to(self.model)
        with self.assertRaises(OSError):
            self.loader(alias).load(_CAS)

    def test_symlinked_parent_denied(self):
        real_parent = self.root / "actual"
        real_parent.mkdir()
        real_model = real_parent / "weights.gguf"
        real_model.write_bytes(_VALID)
        alias = self.root / "shortcut"
        alias.symlink_to(real_parent, target_is_directory=True)
        with self.assertRaises(OSError):
            self.loader(alias / "weights.gguf").load(_CAS)

    def test_hardlinked_model_denied(self):
        alias = self.root / "linked.gguf"
        os.link(self.model, alias)
        with self.assertRaisesRegex(ValueError, "non-hardlinked"):
            self.loader().load(_CAS)

    def test_fifo_denied_without_blocking(self):
        if not hasattr(os, "mkfifo"):
            self.skipTest("FIFO unavailable")
        pipe = self.root / "injected.gguf"
        os.mkfifo(pipe)
        if not stat.S_ISFIFO(pipe.lstat().st_mode):
            self.fail("FIFO fixture identity changed")
        with self.assertRaisesRegex(ValueError, "regular"):
            self.loader(pipe).load(_CAS)

    def test_parent_traversal_is_rejected(self):
        path = self.root / "subdir" / ".." / "weights.gguf"
        with self.assertRaisesRegex(ValueError, "traverse"):
            self.loader(path).load(_CAS)

    def test_inplace_mutation_during_read_invalidates_receipt(self):
        loader = self.loader()
        original_read = os.read
        modified = False

        def mutating_read(descriptor, size):
            nonlocal modified
            payload = original_read(descriptor, size)
            if payload and not modified:
                modified = True
                with open(self.model, "ab") as handle:
                    handle.write(b"changed-during-verification")
                    handle.flush()
                    os.fsync(handle.fileno())
            return payload

        with patch.object(model_loader.os, "read", side_effect=mutating_read):
            with self.assertRaisesRegex(OSError, "changed during verification"):
                loader.load(_CAS)
        self.assertTrue(modified)
        self.assertIsNone(loader.digest)
        self.assertFalse(loader.loaded)

    def test_path_replacement_during_read_invalidates_receipt(self):
        loader = self.loader()
        original_read = os.read
        replaced = False
        old_path = self.root / "orphaned.gguf"

        def replacing_read(descriptor, size):
            nonlocal replaced
            payload = original_read(descriptor, size)
            if payload and not replaced:
                replaced = True
                self.model.rename(old_path)
                self.model.write_bytes(_VALID)
            return payload

        with patch.object(model_loader.os, "read", side_effect=replacing_read):
            with self.assertRaisesRegex(OSError, "changed during verification|replaced during verification|path changed|path rebound"):
                loader.load(_CAS)
        self.assertTrue(replaced)
        self.assertFalse(loader.loaded)
        self.assertIsNone(loader.digest)

    def test_invalid_cas_does_not_touch_weights(self):
        before = self.model.stat()
        with self.assertRaises(PermissionError):
            self.loader().load("no")
        after = self.model.stat()
        self.assertEqual((before.st_dev, before.st_ino, before.st_size), (after.st_dev, after.st_ino, after.st_size))
        self.assertEqual(hashlib.sha256(self.model.read_bytes()).hexdigest(), hashlib.sha256(_VALID).hexdigest())


if __name__ == "__main__":
    unittest.main()
