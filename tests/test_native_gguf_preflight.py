"""Adversarial host-portable source-custody tests for bounded GGUF preflight."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
import struct
import tempfile
import unittest
from unittest.mock import patch

from skeleton.native.gguf_preflight import GGUFPreflightError, inspect_gguf


_SUPPORTED = (os.name == "posix" and hasattr(os, "O_NOFOLLOW")
              and hasattr(os, "O_DIRECTORY") and os.open in os.supports_dir_fd
              and os.stat in os.supports_dir_fd)


@unittest.skipUnless(_SUPPORTED, "POSIX no-follow descriptor custody required")
class GGUFPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gguf-preflight-", dir=Path.home())
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "model.gguf"
        self.data = b"GGUF" + struct.pack("<IQQ", 3, 1, 0) + b"payload"
        self.path.write_bytes(self.data)
        self.path.chmod(0o600)
        self.digest = hashlib.sha256(self.data).hexdigest()

    def test_valid_header_exact_digest(self):
        result = inspect_gguf(self.path, expected_sha256=self.digest)
        self.assertEqual((result.version, result.tensor_count, result.metadata_count), (3, 1, 0))
        self.assertEqual(result.file_size, len(self.data))
        self.assertEqual(result.sha256, self.digest)

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

    def test_symlink_file_denied(self):
        alias = Path(self.temp.name) / "alias.gguf"
        alias.symlink_to(self.path)
        with self.assertRaises(GGUFPreflightError):
            inspect_gguf(alias, expected_sha256=self.digest)

    def test_symlinked_parent_denied(self):
        alias = Path(self.temp.name) / "parent-link"
        alias.symlink_to(Path(self.temp.name), target_is_directory=True)
        with self.assertRaises(GGUFPreflightError):
            inspect_gguf(alias / self.path.name, expected_sha256=self.digest)

    def test_writable_parent_denied(self):
        folder = Path(self.temp.name) / "public"
        folder.mkdir(mode=0o700)
        (folder / "model.gguf").write_bytes(self.data)
        folder.chmod(0o777)
        with self.assertRaisesRegex(GGUFPreflightError, "writable"):
            inspect_gguf(folder / "model.gguf", expected_sha256=self.digest)

    def test_hardlinked_model_denied(self):
        alias = Path(self.temp.name) / "hardlink.gguf"
        os.link(self.path, alias)
        with self.assertRaisesRegex(GGUFPreflightError, "hardlink"):
            inspect_gguf(self.path, expected_sha256=self.digest)

    def test_group_writable_model_denied(self):
        self.path.chmod(0o660)
        with self.assertRaisesRegex(GGUFPreflightError, "permissions"):
            inspect_gguf(self.path, expected_sha256=self.digest)

    def test_relative_dotdot_denied_even_if_normalizes_inside_root(self):
        variant = self.path.parent / ".." / self.path.parent.name / self.path.name
        with self.assertRaisesRegex(GGUFPreflightError, "noncanonical"):
            inspect_gguf(variant, expected_sha256=self.digest)

    def test_atomic_path_swap_denied_after_read(self):
        other = Path(self.temp.name) / "replacement.gguf"
        other.write_bytes(self.data)
        other.chmod(0o600)
        original_read = os.read
        swapped = False

        def swap_after_first_read(fd, amount):
            nonlocal swapped
            data = original_read(fd, amount)
            if not swapped:
                swapped = True
                os.replace(other, self.path)
            return data

        with patch("skeleton.native.gguf_preflight.os.read", side_effect=swap_after_first_read):
            with self.assertRaisesRegex(GGUFPreflightError, "changed"):
                inspect_gguf(self.path, expected_sha256=self.digest)
        self.assertTrue(swapped)


    def test_mutating_pathlike_is_frozen_at_initial_descriptor_open(self):
        path = self.path
        invalid = Path(self.temp.name) / "different.gguf"
        invalid.write_bytes(b"not a model")
        invalid.chmod(0o600)

        class VolatilePath(os.PathLike[str]):
            calls = 0

            def __fspath__(self):
                self.calls += 1
                return str(path if self.calls == 1 else invalid)

        candidate = VolatilePath()
        receipt = inspect_gguf(candidate, expected_sha256=self.digest)
        self.assertEqual(receipt.sha256, self.digest)
        self.assertEqual(candidate.calls, 1)

    def test_replaced_parent_denied_even_with_identical_bytes(self):
        parent = Path(self.temp.name) / "active"
        parent.mkdir(mode=0o700)
        model = parent / "model.gguf"
        model.write_bytes(self.data)
        model.chmod(0o600)
        old_parent = Path(self.temp.name) / "old-parent"
        original_read = os.read
        moved = False

        def swap_parent(fd, amount):
            nonlocal moved
            data = original_read(fd, amount)
            if not moved:
                moved = True
                os.rename(parent, old_parent)
                parent.mkdir(mode=0o700)
                replacement = parent / "model.gguf"
                replacement.write_bytes(self.data)
                replacement.chmod(0o600)
            return data

        with patch("skeleton.native.gguf_preflight.os.read", side_effect=swap_parent):
            with self.assertRaisesRegex(GGUFPreflightError, "parent"):
                inspect_gguf(model, expected_sha256=self.digest)
        self.assertTrue(moved)

    def test_parent_permissions_changed_mid_read_denied(self):
        parent = Path(self.temp.name) / "mutable"
        parent.mkdir(mode=0o700)
        model = parent / "model.gguf"
        model.write_bytes(self.data)
        model.chmod(0o600)
        original_read = os.read
        changed = False

        def open_writes_mid_read(fd, amount):
            nonlocal changed
            data = original_read(fd, amount)
            if not changed:
                changed = True
                parent.chmod(0o777)
            return data

        with patch("skeleton.native.gguf_preflight.os.read",
                   side_effect=open_writes_mid_read):
            with self.assertRaises(GGUFPreflightError):
                inspect_gguf(model, expected_sha256=self.digest)
        self.assertTrue(changed)

    def test_model_replacement_with_same_digest_denied(self):
        new_path = Path(self.temp.name) / "same-digest.gguf"
        new_path.write_bytes(self.data)
        new_path.chmod(0o600)
        original_read = os.read
        changed = False

        def replace_identical_file(fd, amount):
            nonlocal changed
            data = original_read(fd, amount)
            if not changed:
                changed = True
                os.replace(new_path, self.path)
            return data

        with patch("skeleton.native.gguf_preflight.os.read",
                   side_effect=replace_identical_file):
            with self.assertRaisesRegex(GGUFPreflightError, "changed"):
                inspect_gguf(self.path, expected_sha256=self.digest)
        self.assertTrue(changed)



if __name__ == "__main__":
    unittest.main()
