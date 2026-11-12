"""Adversarial descriptor, hardlink, ancestor and race custody regressions.

A verified GGUF header plus SHA is not proof of native model inference, device
compatibility, signed provenance or a model license. Keep these holds distinct.
"""
from __future__ import annotations

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
        with self.assertRaises(ValueError, match="non-hardlinked"):
            self.qualify(self.model)
        with self.assertRaises(ValueError, match="non-hardlinked"):
            self.qualify(alias)

    def test_explicit_parent_traversal_is_disallowed(self):
        unsafe = str(self.private) + "/../private/" + self.model.name
        with self.assertRaises(ValueError, match="parent components"):
            model_loader.ModelLoader(
                unsafe, expected_sha256=self.digest, license_accepted=True
            ).load(AUTH)

    def test_unexpected_content_change_never_preserves_success(self):
        self.model.write_bytes(model_bytes(b"b"))
        with self.assertRaises(ValueError, match="SHA-256 mismatch"):
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
            with self.assertRaises(OSError, match="rebound"):
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
    unittest.main()
