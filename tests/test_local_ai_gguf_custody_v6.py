"""Regression tests for fail-closed GGUF artifact qualification."""
import hashlib
import struct
import tempfile
import unittest
from pathlib import Path

from skeleton.local_ai.model_loader import ModelLoader


class ModelLoaderCustodyTests(unittest.TestCase):
    CAS = "a" * 32

    def test_absent_model_does_not_simulate_success(self):
        with self.assertRaises(FileNotFoundError):
            ModelLoader().load(self.CAS, license_accepted=True)

    def test_missing_digest_is_denied(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "model.gguf"
            path.write_bytes(b"GGUF" + struct.pack("<IQQ", 3, 1, 1) + b"sample-weights")
            with self.assertRaises(ValueError):
                ModelLoader(str(path)).load(self.CAS, license_accepted=True)

    def test_valid_artifact_is_verified_not_inferred(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "model.gguf"
            payload = b"GGUF" + struct.pack("<IQQ", 3, 1, 1) + b"sample-weights"
            path.write_bytes(payload)
            digest = hashlib.sha256(payload).hexdigest()
            loader = ModelLoader(str(path), expected_sha256=digest)
            result = loader.load(self.CAS, license_accepted=True)
            self.assertEqual(result["status"], "artifact_verified_only")
            self.assertEqual(result["digest"], digest)
            self.assertFalse(loader.loaded)
            self.assertFalse(loader.verify(digest))

    def test_mismatch_and_non_gguf_fail_closed(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "model.gguf"
            path.write_bytes(b"not-a-gguf")
            with self.assertRaises(ValueError):
                ModelLoader(str(path), expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest()).load(self.CAS, license_accepted=True)
            path.write_bytes(b"GGUF" + struct.pack("<IQQ", 3, 1, 1) + b"sample-weights")
            with self.assertRaises(ValueError):
                ModelLoader(str(path), expected_sha256="0" * 64).load(self.CAS, license_accepted=True)

    def test_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "real.gguf"
            path.write_bytes(b"GGUF" + struct.pack("<IQQ", 3, 1, 1) + b"sample-weights")
            link = Path(root) / "link.gguf"
            link.symlink_to(path)
            with self.assertRaises(OSError):
                ModelLoader(str(link), expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest()).load(self.CAS, license_accepted=True)


if __name__ == "__main__":
    unittest.main()
