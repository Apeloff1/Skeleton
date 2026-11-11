"""Fail-closed token-file custody regressions for studio readiness."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skeleton.app.studio_readiness import _private_token


class PrivateTokenCustodyTests(unittest.TestCase):
    def test_private_regular_token_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "token"
            path.write_text("A" * 32, encoding="ascii")
            if os.name != "nt":
                path.chmod(0o600)
            self.assertEqual(_private_token(path), "A" * 32)

    @unittest.skipIf(os.name == "nt", "POSIX hardlink custody")
    def test_hardlinked_token_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "token"
            path.write_text("A" * 32, encoding="ascii")
            path.chmod(0o600)
            os.link(path, Path(directory) / "alias")
            with self.assertRaises(ValueError):
                _private_token(path)

    def test_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "real"
            target.write_text("A" * 32, encoding="ascii")
            if os.name != "nt":
                target.chmod(0o600)
            link = Path(directory) / "link"
            try:
                link.symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            with self.assertRaises((ValueError, OSError)):
                _private_token(link)

    def test_path_replacement_after_open_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "token"
            replacement = Path(directory) / "replacement"
            path.write_text("A" * 32, encoding="ascii")
            replacement.write_text("B" * 32, encoding="ascii")
            if os.name != "nt":
                path.chmod(0o600)
                replacement.chmod(0o600)
            original_lstat = os.lstat
            count = 0

            def swap_on_second_stat(value, *args, **kwargs):
                nonlocal count
                if Path(value) == path:
                    count += 1
                    if count == 2:
                        os.replace(replacement, path)
                return original_lstat(value, *args, **kwargs)

            with patch("skeleton.app.studio_readiness.os.lstat", side_effect=swap_on_second_stat):
                with self.assertRaises(ValueError):
                    _private_token(path)


if __name__ == "__main__":
    unittest.main()
