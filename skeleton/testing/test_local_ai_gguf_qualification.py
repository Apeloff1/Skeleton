"""Regression tests for the legacy local AI fail-closed GGUF boundary."""
import hashlib
import tempfile
import unittest
from pathlib import Path

from skeleton.local_ai.model_loader import ModelLoader
from skeleton.local_ai.inference_loop import InferenceLoop

CAS = "approved-cas-token-123456"


class ModelQualificationTests(unittest.TestCase):
    def test_pinned_artifact_is_not_inference(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "model.gguf"
            payload = b"GGUF" + (3).to_bytes(4, "little") + b"test-fixture-not-real-weights"
            path.write_bytes(payload)
            digest = hashlib.sha256(payload).hexdigest()
            loader = ModelLoader(str(path), expected_sha256=digest, license_accepted=True)
            receipt = loader.load(CAS)
            self.assertEqual(receipt["status"], "artifact_verified_not_loaded")
            self.assertEqual(receipt["digest"], digest)
            self.assertFalse(loader.loaded)
            self.assertFalse(loader.verify(digest))

    def test_missing_model_is_not_simulated(self):
        with self.assertRaises(FileNotFoundError):
            ModelLoader("/missing/nonexistent.gguf", expected_sha256="0" * 64, license_accepted=True).load(CAS)

    def test_license_and_digest_required(self):
        with self.assertRaises(PermissionError):
            ModelLoader("model.gguf", expected_sha256="0" * 64).load(CAS)
        with self.assertRaises(ValueError):
            ModelLoader("model.gguf", license_accepted=True).load(CAS)

    def test_bad_header_and_hash_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "bad.gguf"
            path.write_bytes(b"NOTG" + (3).to_bytes(4, "little"))
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaises(ValueError):
                ModelLoader(str(path), expected_sha256=digest, license_accepted=True).load(CAS)
            path.write_bytes(b"GGUF" + (3).to_bytes(4, "little"))
            with self.assertRaises(ValueError):
                ModelLoader(str(path), expected_sha256=digest, license_accepted=True).load(CAS)

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "real.gguf"
            target.write_bytes(b"GGUF" + (3).to_bytes(4, "little"))
            link = Path(root) / "link.gguf"
            link.symlink_to(target)
            with self.assertRaises(OSError):
                ModelLoader(str(link), expected_sha256=hashlib.sha256(target.read_bytes()).hexdigest(), license_accepted=True).load(CAS)

    def test_placeholder_inference_refuses(self):
        with self.assertRaisesRegex(RuntimeError, "LOCAL_GGUF_NOT_ACTIVATED"):
            list(InferenceLoop().run("hello", CAS))
        with self.assertRaisesRegex(RuntimeError, "LOCAL_GGUF_NOT_ACTIVATED"):
            InferenceLoop().complete("hello", CAS)


if __name__ == "__main__":
    unittest.main()
