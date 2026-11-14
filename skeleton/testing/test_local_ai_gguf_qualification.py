"""Reconciled independent source-custody regressions from Jeeves and Dragon.

Artificial artifact fixtures never establish native model or release qualification.
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


# Independent Dragon donor cases retained during integration.
import hashlib
import os
import struct
import tempfile
import unittest
from pathlib import Path

from skeleton.local_ai.model_loader import ModelLoader, _MIN_GGUF_BYTES

AUTH = "a" * 32


def artifact(*, version: int = 3, tensors: int = 1,
             metadata: int = 1, payload: bytes = b"Q" * 128) -> bytes:
    return b"GGUF" + struct.pack("<IQQ", version, tensors, metadata) + payload


@unittest.skipUnless(os.name == "posix" and hasattr(os, "O_NOFOLLOW"),
                     "descriptor-custody verification requires a POSIX host")
class GGUFArtifactQualificationTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="skeleton-gguf-qualification-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.path = self.root / "model.gguf"
        self.data = artifact()
        self.path.write_bytes(self.data)
        self.sha = hashlib.sha256(self.data).hexdigest()

    def loader(self, path: Path | None = None, **kwargs):
        return ModelLoader(str(self.path if path is None else path),
                           expected_sha256=self.sha,
                           license_accepted=True, **kwargs)

    def test_true_descriptor_verified_artifact_stays_unloaded(self):
        loader = self.loader()
        receipt = loader.load(AUTH)
        self.assertEqual(receipt["status"], "artifact_verified_not_loaded")
        self.assertEqual(receipt["digest"], self.sha)
        self.assertEqual(receipt["bytes"], len(self.data))
        self.assertEqual(Path(receipt["path"]), self.path)
        self.assertFalse(loader.loaded)
        self.assertFalse(loader.verify(self.sha))
        self.assertEqual(loader.digest, self.sha)

    def test_license_and_cas_are_separate_required_authorities(self):
        denied = ModelLoader(str(self.path), expected_sha256=self.sha)
        with self.assertRaises(PermissionError):
            denied.load(AUTH)
        with self.assertRaises(PermissionError):
            self.loader().load("")
        with self.assertRaises(PermissionError):
            self.loader().load("short")
        with self.assertRaises(PermissionError):
            self.loader().load(None)
        self.assertFalse(denied.loaded)

    def test_expected_digest_requires_exact_lowercase_sha256(self):
        for value in (True, 5, "", "a" * 63, "A" * 64, "g" * 64):
            with self.subTest(value=value):
                loader = self.loader()
                with self.assertRaises(ValueError):
                    loader.load(AUTH, expected_sha256=value)
                self.assertIsNone(loader.digest)
                self.assertFalse(loader.loaded)
        loader = self.loader()
        with self.assertRaisesRegex(ValueError, "mismatch"):
            loader.load(AUTH, expected_sha256="0" * 64)
        self.assertFalse(loader.verify("0" * 64))

    def test_v2_v3_supported_but_unknown_and_empty_models_rejected(self):
        for version in (2, 3):
            self.path.write_bytes(artifact(version=version))
            digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
            loader = self.loader()
            receipt = loader.load(AUTH, expected_sha256=digest)
            self.assertEqual(receipt["status"], "artifact_verified_not_loaded")
            self.assertFalse(loader.loaded)
        for version, tensors, metadata in (
            (1, 1, 1), (4, 1, 1), (3, 0, 1), (3, 1, 0),
            (3, 2**64 - 1, 1), (3, 1, 2**64 - 1),
        ):
            self.path.write_bytes(artifact(version=version, tensors=tensors, metadata=metadata))
            digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
            with self.subTest(version=version, tensors=tensors, metadata=metadata):
                loader = self.loader()
                with self.assertRaises(ValueError, msg="invalid GGUF promoted"):
                    loader.load(AUTH, expected_sha256=digest)
                self.assertFalse(loader.loaded)

    def test_short_bad_magic_and_missing_payload_cannot_qualify(self):
        for contents in (
            b"",
            b"GGUF",
            b"GGUF" + struct.pack("<IQQ", 3, 1, 1),
            b"GGZX" + struct.pack("<IQQ", 3, 1, 1) + b"M",
            b"MZ" + b"\x00" * 180,
        ):
            self.path.write_bytes(contents)
            loader = self.loader()
            with self.subTest(length=len(contents)), self.assertRaises(ValueError):
                loader.load(AUTH, expected_sha256=hashlib.sha256(contents).hexdigest())
            self.assertFalse(loader.loaded)

    def test_byte_budget_is_bounded_not_boolean(self):
        for max_bytes in (False, True, 0, -1, 2**41, _MIN_GGUF_BYTES - 1):
            with self.subTest(max_bytes=max_bytes), self.assertRaises(ValueError):
                self.loader().load(AUTH, max_bytes=max_bytes)
        for limit in (len(self.data) - 1, _MIN_GGUF_BYTES):
            loader = self.loader()
            with self.assertRaises(ValueError):
                loader.load(AUTH, max_bytes=limit)
            self.assertIsNone(loader.digest)

    def test_no_model_path_never_becomes_a_dummy_success(self):
        loader = ModelLoader(None, expected_sha256=self.sha, license_accepted=True)
        with self.assertRaises(FileNotFoundError):
            loader.load(AUTH)
        with self.assertRaises(FileNotFoundError):
            self.loader(self.root / "not-present.gguf").load(AUTH)
        self.assertFalse(loader.loaded)

    def test_auth_and_digest_cannot_reuse_a_previous_success(self):
        loader = self.loader()
        self.assertEqual(loader.load(AUTH)["digest"], self.sha)
        with self.assertRaises(PermissionError):
            loader.load("short")
        self.assertIsNone(loader.digest)
        self.assertFalse(loader.loaded)
        self.assertFalse(loader.verify(self.sha))


if __name__ == "__main__":
    import unittest
    unittest.main()
