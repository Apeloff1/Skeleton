"""Cross-boundary regression: structural checks cannot certify legacy GGUF inference."""
from __future__ import annotations

import hashlib
import os
import struct
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from skeleton.local_ai import doctor as doctor_module
from skeleton.local_ai import health as health_module
from skeleton.local_ai.inference_loop import InferenceLoop
from skeleton.local_ai.model_loader import ModelLoader
from skeleton.local_ai.operational_engine import (
    LocalInferenceNotActivated, OperationalEngine,
)

CAS = "a" * 32


class NativeReadinessContinuityTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "posix", "descriptor qualification requires POSIX")
    def test_verified_artifact_never_unlocks_legacy_generation(self):
        with tempfile.TemporaryDirectory() as root:
            artifact = Path(root) / "source.gguf"
            payload = b"GGUF" + struct.pack("<IQQ", 3, 1, 1) + b"synthetic-source-custody" * 4
            artifact.write_bytes(payload)
            digest = hashlib.sha256(payload).hexdigest()
            loader = ModelLoader(
                str(artifact), expected_sha256=digest, license_accepted=True,
            )
            receipt = loader.load(CAS)
            self.assertEqual(receipt["status"], "artifact_verified_not_loaded")
            self.assertFalse(loader.loaded)
            self.assertFalse(loader.verify(digest))
            loader.loaded = True
            self.assertFalse(loader.verify(digest))
            with self.assertRaises(LocalInferenceNotActivated):
                OperationalEngine().generate("hello", CAS)
            with self.assertRaisesRegex(RuntimeError, "LOCAL_GGUF_NOT_ACTIVATED"):
                list(InferenceLoop().run("hello", CAS))

    def test_complete_structural_seams_cannot_pass_native_doctor(self):
        class StructuralOnly:
            def status(self):
                return {
                    "seams": health_module.__seams__,
                    "status": "complete",
                    "adapter": True,
                    "bridge": True,
                }

        with patch.object(health_module, "get_complete", return_value=StructuralOnly()):
            status = health_module.health()
        self.assertTrue(status["healthy"])
        self.assertIs(status["inference_ready"], False)
        self.assertIsNone(status["readiness_evidence"])
        with patch.object(doctor_module, "health", return_value=status):
            diagnosis = doctor_module.doctor()
        self.assertEqual(diagnosis["doctor"], "failed")


    def test_legacy_cas_is_a_bounded_exact_string(self):
        from skeleton.local_ai.fail_closed import guard_cas
        class Hostile(str):
            def __len__(self):
                raise AssertionError("untrusted length hook")
        for invalid in (None, [1] * 32, b"a" * 32, Hostile(CAS), "x" * 4097):
            with self.subTest(kind=type(invalid).__name__), self.assertRaises(PermissionError):
                guard_cas(invalid)
        guard_cas(CAS)

    @unittest.skipUnless(os.name == "posix", "descriptor qualification requires POSIX")
    def test_invalid_header_stops_before_full_artifact_hashing(self):
        from skeleton.local_ai import model_loader as module
        with tempfile.TemporaryDirectory() as root:
            artifact = Path(root) / "invalid.gguf"
            payload = b"NOPE" + struct.pack("<IQQ", 3, 1, 1) + b"x" * 4096
            artifact.write_bytes(payload)
            loader = ModelLoader(str(artifact), expected_sha256=hashlib.sha256(payload).hexdigest(),
                                 license_accepted=True)
            original = module.os.read
            reads = []
            def read(fd, count):
                reads.append(count)
                return original(fd, count)
            with patch.object(module, "_CHUNK", 64), patch.object(module.os, "read", read):
                with self.assertRaisesRegex(ValueError, "GGUF"):
                    loader.load(CAS)
            self.assertEqual(reads, [64])
            self.assertIsNone(loader.digest)


if __name__ == "__main__":
    unittest.main()
