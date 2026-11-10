"""Regression tests for the legacy facade's fail-closed behavior."""
import unittest
from unittest.mock import patch

from skeleton.jeeves.local_inference_bridge import Bridge
from skeleton.local_ai.local_ai_complete import LocalAIComplete
from skeleton.local_ai import bootstrap_cli


class LegacyLocalAIReadinessTests(unittest.TestCase):
    def test_inventory_does_not_claim_inference(self):
        status = LocalAIComplete().status()
        self.assertIs(status["ready"], False)
        self.assertEqual(status["status"], "unavailable")
        self.assertEqual(status["readiness_code"], "LOCAL_INFERENCE_NOT_BOUND")

    def test_bridge_never_returns_synthetic_model_text(self):
        with self.assertRaisesRegex(RuntimeError, "LOCAL_INFERENCE_NOT_BOUND"):
            Bridge().dispatch({"prompt": "hello"}, "a" * 32)

    def test_invalid_cas_denied_before_dispatch(self):
        with self.assertRaises(PermissionError):
            Bridge().dispatch({"prompt": "hello"}, "short")

    def test_non_mapping_command_denied(self):
        with self.assertRaises(TypeError):
            Bridge().dispatch(None, "a" * 32)

    def test_cli_reports_nonzero_unready(self):
        with patch("sys.argv", ["bootstrap_cli", "--status"]):
            self.assertEqual(bootstrap_cli.main(), 2)


if __name__ == "__main__":
    unittest.main()
