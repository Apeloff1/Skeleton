"""Native offline acceptance: real execution receipts are scoped, never quality claims."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
import unittest
from unittest.mock import patch

from skeleton.app.local_ai_acceptance import ACCEPTANCE_SCHEMA, run_offline_acceptance
from skeleton.app.cli import run_app_cli
from skeleton.app.windows_launcher import main as frozen_main


def _mock_smokes(native=True, training=True, benchmark=True):
    return (
        patch("skeleton.app.local_ai.smoke_offline_native_inference", return_value=native),
        patch("skeleton.app.local_ai_training.smoke_offline_native_training", return_value=training),
        patch("skeleton.app.local_ai_benchmark.smoke_offline_native_benchmark", return_value=benchmark),
    )


class TestNativeOfflineAcceptance(unittest.TestCase):
    def test_all_scoped_smokes_pass_without_claiming_model_qualification(self):
        a, b, c = _mock_smokes()
        with a, b, c:
            result = run_offline_acceptance()
        self.assertEqual(result["schema"], ACCEPTANCE_SCHEMA)
        self.assertTrue(result["passed"])
        self.assertEqual(result["checks_total"], 3)
        self.assertEqual(result["checks_passed"], 3)
        self.assertEqual(len(result["checks"]), 3)
        self.assertFalse(result["enterprise_release_qualified"])
        self.assertFalse(result["general_model_quality_certified"])
        self.assertFalse(result["gguf_model_qualified"])
        self.assertFalse(result["independent_security_certified"])
        self.assertFalse(result["external_model_downloaded"])

    def test_failing_step_is_not_masked_by_successful_other_checks(self):
        a, b, c = _mock_smokes(training=False)
        with a, b, c:
            result = run_offline_acceptance()
        self.assertFalse(result["passed"])
        self.assertEqual(result["checks_passed"], 2)
        self.assertEqual(
            result["checks"][1],
            {"name": "cpu_gradient_checkpoint_and_inference",
             "passed": False, "failure_kind": "CheckReturnedFalse"},
        )

    def test_exception_payload_remains_private_and_failure_is_counted(self):
        a, b, c = _mock_smokes()
        with a, b, c:
            with patch(
                "skeleton.app.local_ai_training.smoke_offline_native_training",
                side_effect=RuntimeError("PRIVATE DATA AND PATH MUST NOT LEAK"),
            ):
                result = run_offline_acceptance()
        self.assertFalse(result["passed"])
        self.assertEqual(result["checks"][1]["failure_kind"], "RuntimeError")
        self.assertNotIn("PRIVATE", json.dumps(result))

    def test_non_boolean_step_is_not_coerced_to_success(self):
        a, b, c = _mock_smokes(native=1)
        with a, b, c:
            result = run_offline_acceptance()
        self.assertFalse(result["passed"])
        self.assertEqual(result["checks"][0]["failure_kind"], "InvalidCheckResult")

    def test_cli_and_installed_entry_share_same_acceptance_semantics(self):
        a, b, c = _mock_smokes()
        with a, b, c:
            for args in (
                ["local-ai", "--self-check", "--json"],
                ["--offline-command", "local-ai", "--self-check", "--json"],
            ):
                with self.subTest(command=args):
                    out = StringIO()
                    with redirect_stdout(out):
                        code = frozen_main(args) if args[0] == "--offline-command" else run_app_cli(args)
                    self.assertEqual(code, 0, out.getvalue())
                    report = json.loads(out.getvalue())
                    self.assertTrue(report["passed"])
                    self.assertFalse(report["general_model_quality_certified"])

    def test_cli_self_check_propagates_failing_status_not_false_success(self):
        a, b, c = _mock_smokes(benchmark=False)
        with a, b, c, redirect_stdout(out := StringIO()):
            result = run_app_cli(["local-ai", "--self-check", "--json"])
        self.assertEqual(result, 1)
        self.assertFalse(json.loads(out.getvalue())["passed"])

    def test_cli_rejects_mixed_modes_before_running_any_check(self):
        examples = (
            ["--self-check", "--model", "private.json"],
            ["--self-check", "--prompt", "hello"],
            ["--self-check", "--gguf-model", "weights.gguf", "--llama-executable", "llama-cli"],
            ["--self-check", "--train-corpus", "private.txt"],
            ["--self-check", "--benchmark-suite", "suite.json"],
            ["--self-check", "--max-output-tokens", "10"],
            ["--self-check", "--epochs", "1"],
        )
        with patch(
            "skeleton.app.local_ai_acceptance.run_offline_acceptance",
            side_effect=AssertionError("mixed mode must never start a self-check"),
        ):
            for extra in examples:
                with self.subTest(extra=extra), redirect_stdout(StringIO()):
                    self.assertEqual(run_app_cli(["local-ai", *extra]), 2)


if __name__ == "__main__":
    unittest.main()
