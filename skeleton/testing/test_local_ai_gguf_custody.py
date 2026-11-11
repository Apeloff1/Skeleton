"""Adversarial no-follow path-custody checks for the local GGUF artifact verifier."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from skeleton.local_ai import model_loader
from skeleton.local_ai.model_loader import ModelLoader

CAS = "approved-cas-token-123456"
POSIX_CUSTODY = (
    os.name == "posix"
    and hasattr(os, "O_NOFOLLOW")
    and hasattr(os, "O_DIRECTORY")
    and os.open in os.supports_dir_fd
)


def _artifact(path: Path, suffix: bytes = b"source-custody") -> str:
    payload = b"GGUF" + (3).to_bytes(4, "little") + suffix
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


@unittest.skipUnless(POSIX_CUSTODY, "secure POSIX dir_fd/NOFOLLOW unavailable")
class LocalGGUFPathCustodyTests(unittest.TestCase):
    def test_regular_artifact_is_verified_but_never_activated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.gguf"
            expected = _artifact(path)
            loader = ModelLoader(str(path), expected_sha256=expected, license_accepted=True)
            receipt = loader.load(CAS)
            self.assertEqual(receipt["status"], "artifact_verified_not_loaded")
            self.assertEqual(receipt["digest"], expected)
            self.assertFalse(loader.loaded)
            self.assertFalse(loader.verify(expected))

    def test_hardlinked_model_is_refused_even_when_path_is_regular(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.gguf"
            expected = _artifact(path)
            os.link(path, Path(directory) / "alias.gguf")
            loader = ModelLoader(str(path), expected_sha256=expected, license_accepted=True)
            with self.assertRaisesRegex(ValueError, "size/type"):
                loader.load(CAS)
            self.assertFalse(loader.loaded)
            self.assertIsNone(loader.digest)

    def test_intermediate_symlink_directory_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real = root / "real"
            real.mkdir()
            expected = _artifact(real / "model.gguf")
            (root / "redirect").symlink_to(real, target_is_directory=True)
            loader = ModelLoader(str(root / "redirect" / "model.gguf"),
                                 expected_sha256=expected, license_accepted=True)
            with self.assertRaises(OSError):
                loader.load(CAS)
            self.assertFalse(loader.loaded)

    def test_replacement_between_read_and_final_path_verification_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.gguf"
            expected = _artifact(path)
            actual_open = model_loader._open_guarded_model
            calls = 0

            def replace_on_second_open(model_path: Path):
                nonlocal calls
                calls += 1
                if calls == 2:
                    path.replace(Path(directory) / "old.gguf")
                    _artifact(path, b"new-source-binary")
                return actual_open(model_path)

            loader = ModelLoader(str(path), expected_sha256=expected, license_accepted=True)
            with patch.object(model_loader, "_open_guarded_model",
                              side_effect=replace_on_second_open):
                with self.assertRaisesRegex(RuntimeError, "path replaced"):
                    loader.load(CAS)
            self.assertEqual(calls, 2)
            self.assertFalse(loader.loaded)
            self.assertIsNone(loader.digest)


if __name__ == "__main__":
    unittest.main()
