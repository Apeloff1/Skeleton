"""Reconciled independent source-custody regressions from Jeeves and Dragon.

Artificial artifact fixtures never establish native model or release qualification.
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


# Independent Dragon donor cases retained during integration.
import hashlib
import os
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from skeleton.local_ai import model_loader

AUTH = "operator-cas-verified-" + "x" * 24


def model_bytes(letter=b"a"):
    return b"GGUF" + struct.pack("<IQQ", 3, 1, 1) + letter * 256


@unittest.skipUnless(os.name == "posix" and hasattr(os, "O_NOFOLLOW"),
                     "POSIX no-follow file custody required")
class GGUFDescriptorCustodyTest(unittest.TestCase):
    def setUp(self):
        context = tempfile.TemporaryDirectory(prefix="skeleton-gguf-custody-")
        self.addCleanup(context.cleanup)
        self.root = Path(context.name)
        self.private = self.root / "private"
        self.private.mkdir()
        self.model = self.private / "verified.gguf"
        self.contents = model_bytes()
        self.model.write_bytes(self.contents)
        self.digest = hashlib.sha256(self.contents).hexdigest()

    def qualify(self, path=None, expected=None):
        return model_loader.ModelLoader(
            str(self.model if path is None else path),
            expected_sha256=self.digest if expected is None else expected,
            license_accepted=True,
        ).load(AUTH)

    def test_original_private_regular_file_can_be_inspected_only(self):
        verified = self.qualify()
        self.assertEqual(verified["digest"], self.digest)
        self.assertEqual(verified["status"], "artifact_verified_not_loaded")

    def test_symlinked_final_path_never_returns_the_source_digest(self):
        alias = self.private / "alias.gguf"
        alias.symlink_to(self.model)
        with self.assertRaises(OSError):
            self.qualify(alias)

    def test_symlinked_ancestor_is_rejected_before_header_read(self):
        link = self.root / "redirected"
        link.symlink_to(self.private, target_is_directory=True)
        with self.assertRaises(OSError):
            self.qualify(link / self.model.name)

    def test_hardlinked_model_is_rejected_even_with_correct_digest(self):
        alias = self.private / "other.gguf"
        os.link(self.model, alias)
        with self.assertRaisesRegex(ValueError, "non-hardlinked"):
            self.qualify(self.model)
        with self.assertRaisesRegex(ValueError, "non-hardlinked"):
            self.qualify(alias)

    def test_explicit_parent_traversal_is_disallowed(self):
        unsafe = str(self.private) + "/../private/" + self.model.name
        with self.assertRaisesRegex(ValueError, "parent components"):
            model_loader.ModelLoader(
                unsafe, expected_sha256=self.digest, license_accepted=True
            ).load(AUTH)

    def test_unexpected_content_change_never_preserves_success(self):
        self.model.write_bytes(model_bytes(b"b"))
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            self.qualify()

    def test_rebound_model_file_between_final_open_and_rewalk_is_refused(self):
        replacement = self.private / "replacement.gguf"
        replacement.write_bytes(model_bytes(b"b"))
        opener = model_loader._open_guarded_model
        calls = 0

        def swap_before_rewalk(path):
            nonlocal calls
            calls += 1
            if calls == 2:
                os.replace(replacement, self.model)
            return opener(path)

        with mock.patch.object(
            model_loader, "_open_guarded_model", side_effect=swap_before_rewalk,
        ):
            with self.assertRaisesRegex(OSError, "rebound"):
                self.qualify()
        self.assertEqual(calls, 2)

    def test_regular_directory_never_qualifies_as_model(self):
        with self.assertRaises((OSError, ValueError)):
            self.qualify(self.private)

    def test_truncated_or_oversized_header_counters_rejected(self):
        corrupt = b"GGUF" + struct.pack("<IQQ", 3, 2**64 - 1, 1) + b"x"
        self.model.write_bytes(corrupt)
        with self.assertRaises(ValueError):
            self.qualify(expected=hashlib.sha256(corrupt).hexdigest())


if __name__ == "__main__":
    import unittest
    unittest.main()
