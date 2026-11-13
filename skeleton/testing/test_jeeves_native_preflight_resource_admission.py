"""Jeeves native admission resource checks run before any private stdin/model IO."""
from __future__ import annotations

from pathlib import Path
from unittest import mock
import unittest

from skeleton.jeeves.agent.native_operator_preflight import (
    NativeOperatorHold, check_operator_admission,
)
from skeleton.jeeves.agent.native_cli import main as native_main


def admit(**changes):
    options = {
        "mode": "agent",
        "task_stdin": True,
        "session": None,
        "request_id": None,
        "source_root": None,
        "signed_source_manifest": None,
        "enable_source_tool": False,
        "max_sources": 4,
        "max_steps": 8,
        "max_model_calls": 8,
        "max_wall_seconds": 180.0,
    }
    options.update(changes)
    return check_operator_admission(**options)


class ResourcePreflightTests(unittest.TestCase):
    def test_safe_local_cpu_defaults_remain_available(self):
        decision = admit()
        self.assertEqual(decision.context_tokens, 4096)
        self.assertEqual(decision.output_tokens, 1024)
        self.assertEqual(decision.native_threads, 4)
        self.assertEqual(decision.gpu_layers, 0)
        self.assertEqual(decision.capacity_budget_bytes, 8000000000)

    def test_invalid_context_and_output_rejected_before_activation(self):
        for value in (None, True, -1, 0, 127, 131073, 1.5, "4096"):
            with self.subTest(context=value), self.assertRaises(NativeOperatorHold):
                admit(context_tokens=value)
        for value in (None, True, 0, -1, 8193, "8", 2.5):
            with self.subTest(output=value), self.assertRaises(NativeOperatorHold):
                admit(output_tokens=value)
        for value in (128, 1024, 4096):
            with self.subTest(reservation=value), self.assertRaises(NativeOperatorHold):
                admit(context_tokens=value, output_tokens=value)

    def test_invalid_cpu_gpu_and_capacity_cannot_be_coerced(self):
        for field, bad in (
            ("native_threads", (True, 0, -1, 65, "4")),
            ("gpu_layers", (True, -1, 129, "0", 1.5)),
            ("capacity_budget_bytes", (True, 0, -1, 20000000001, "8000000000")),
        ):
            for value in bad:
                with self.subTest(field=field, value=value), self.assertRaises(NativeOperatorHold):
                    admit(**{field: value})

    def test_accepted_input_never_certifies_an_installed_model(self):
        record = admit().public_receipt()
        self.assertFalse(record["may_activate_native"])
        self.assertTrue(record["operator_resource_shape_admissible"])
        self.assertFalse(record["model_rights_verified"])
        self.assertFalse(record["device_qualified"])
        self.assertFalse(record["release_certified"])

    def test_cli_rejects_resource_violations_before_stdin_read(self):
        args = [
            "--model-root", "/private/model",
            "--state-dir", "/private/state",
            "--tenant", "local",
            "--subject", "operator",
            "--mode", "agent",
            "--task-stdin",
            "--context", "64",
        ]
        fake = mock.Mock()
        with (
            mock.patch("sys.stdin", fake),
            mock.patch("skeleton.jeeves.agent.native_cli.activate_checked") as activate,
        ):
            self.assertEqual(native_main(args), 2)
        fake.buffer.read.assert_not_called()
        activate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
