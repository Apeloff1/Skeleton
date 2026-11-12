"""Adversarial GGUF artifact qualification, never a model-inference claim.

These tests use a small invented header solely to exercise the legacy
ModelLoader's fail-closed metadata and digest boundary. They do NOT represent
real GGUF weights, a functional tokenizer, or real model execution.
"""
from __future__ import annotations

import hashlib
import os
import struct
import tempfile
import unittest
from pathlib import Path

from skeleton.local_ai.model_loader import ModelLoader


_CAS = "test-only-authorized-cas-v1"


def _header(*, version: int = 3, tensors: int = 1, metadata: int = 1) -> bytes:
    return b"GGUF" + struct.pack("<IQQ", version, tensors, metadata) + b"synthetic-header-custody-not-inference"


@unittest.skipUnless(os.name == "posix", "Descriptor-based GGUF verification requires POSIX")
class TestLocalAIGGUFQualification(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="local-ai-custody-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "model.gguf"
        self.path.write_bytes(_header())

    def digest(self) -> str:
        return hashlib.sha256(self.path.read_bytes()).hexdigest()

    def loader(self, *, accepted: bool = True, expected: str | None = None) -> ModelLoader:
        return ModelLoader(
            str(self.path),
            expected_sha256=self.digest() if expected is None else expected,
            license_accepted=accepted,
            max_bytes=4096,
        )

    def test_qualified_artifact_is_never_reported_as_loaded_model(self):
        digest = self.digest()
        loader = self.loader()
        receipt = loader.load(_CAS)
        self.assertEqual(receipt["status"], "artifact_verified_not_loaded")
        self.assertEqual(receipt["digest"], digest)
        self.assertEqual(receipt["bytes"], self.path.stat().st_size)
        self.assertEqual(receipt["path"], str(self.path))
        self.assertFalse(loader.loaded)
        self.assertFalse(loader.verify(digest))

    def test_license_explicitly_required(self):
        loader = self.loader(accepted=False)
        with self.assertRaisesRegex(PermissionError, "license acceptance"):
            loader.load(_CAS)
        self.assertIsNone(loader.digest)
        self.assertFalse(loader.loaded)

    def test_cas_cannot_be_absent_or_too_short(self):
        loader = self.loader()
        for cas in ("", "x" * 15):
            with self.subTest(cas_len=len(cas)), self.assertRaises(PermissionError):
                loader.load(cas)
        self.assertFalse(loader.loaded)

    def test_digest_is_full_pinned_lowercase_sha256(self):
        for expected in ("", "a" * 63, "A" * 64, "g" * 64):
            with self.subTest(expected=expected), self.assertRaises(ValueError):
                self.loader(expected=expected).load(_CAS)
        with self.assertRaisesRegex(ValueError, "mismatch"):
            self.loader(expected="0" * 64).load(_CAS)

    def test_wrong_magic_rejected(self):
        self.path.write_bytes(b"NOPE" + _header()[4:])
        with self.assertRaisesRegex(ValueError, "GGUF"):
            self.loader().load(_CAS)

    def test_unsupported_gguf_versions_rejected(self):
        for version in (0, 1, 4, 2**32 - 1):
            with self.subTest(version=version):
                self.path.write_bytes(_header(version=version))
                with self.assertRaisesRegex(ValueError, "header"):
                    self.loader().load(_CAS)

    def test_empty_and_unreasonable_counts_rejected(self):
        for tensors, metadata in ((0, 1), (1, 0), (100000, 1), (1, 100000)):
            with self.subTest(tensors=tensors, metadata=metadata):
                self.path.write_bytes(_header(tensors=tensors, metadata=metadata))
                with self.assertRaisesRegex(ValueError, "header|bounds"):
                    self.loader().load(_CAS)

    def test_truncated_artifact_and_byte_budget_rejected(self):
        self.path.write_bytes(b"GGUF")
        with self.assertRaisesRegex(ValueError, "size"):
            self.loader().load(_CAS)
        self.path.write_bytes(_header() * 3)
        with self.assertRaisesRegex(ValueError, "budget"):
            self.loader().load(_CAS, max_bytes=32)

    def test_invalid_requested_byte_budget_rejected(self):
        for limit in (True, False, 0, 24, 64 * 1024**3 + 1, 3.25):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                self.loader().load(_CAS, max_bytes=limit)

    def test_missing_model_path_is_not_a_loaded_fallback(self):
        loader = ModelLoader(expected_sha256=self.digest(), license_accepted=True)
        with self.assertRaisesRegex(FileNotFoundError, "required"):
            loader.load(_CAS)
        self.assertFalse(loader.loaded)


if __name__ == "__main__":
    unittest.main()
