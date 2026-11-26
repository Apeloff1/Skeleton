"""Fail-closed regression for local-AI structural versus actual model readiness."""
import unittest
from unittest.mock import patch

from skeleton.local_ai import doctor as doctor_module
from skeleton.local_ai import health as health_module


class ReadinessTruthTests(unittest.TestCase):
    def test_structural_complete_never_claims_native_inference(self):
        class Complete:
            def status(self):
                return {"seams": health_module.__seams__, "status": "complete", "adapter": True, "bridge": True}

        with patch.object(health_module, "get_complete", return_value=Complete()):
            result = health_module.health()
        self.assertTrue(result["healthy"])
        self.assertIs(result["inference_ready"], False)
        self.assertEqual(result["readiness_code"], "NATIVE_GGUF_INFERENCE_UNVERIFIED")
        self.assertIsNone(result["readiness_evidence"])

    def test_doctor_denies_structural_only_success(self):
        with patch.object(doctor_module, "health", return_value={"healthy": True, "inference_ready": False, "readiness_evidence": None}):
            result = doctor_module.doctor()
        self.assertEqual(result["doctor"], "failed")

    def test_doctor_denies_missing_evidence_even_with_boolean_ready(self):
        with patch.object(doctor_module, "health", return_value={"healthy": True, "inference_ready": True, "readiness_evidence": None}):
            result = doctor_module.doctor()
        self.assertEqual(result["doctor"], "failed")


if __name__ == "__main__":
    unittest.main()
