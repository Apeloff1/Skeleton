"""Cross-boundary regression: structural checks cannot certify legacy GGUF inference."""
from __future__ import annotations

import hashlib
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
    def test_verified_artifact_never_unlocks_legacy_generation(self):
        with tempfile.TemporaryDirectory() as root:
            artifact = Path(root) / "source.gguf"
            payload = b"GGUF" + (3).to_bytes(4, "little") + b"not-a-model"
            artifact.write_bytes(payload)
            digest = hashlib.sha256(payload).hexdigest()
            loader = ModelLoader(
                str(artifact), expected_sha256=digest, license_accepted=True,
            )
            receipt = loader.load(CAS)
            self.assertEqual(receipt["status"], "artifact_verified_not_loaded")
            self.assertFalse(loader.loaded)
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


if __name__ == "__main__":
    unittest.main()
