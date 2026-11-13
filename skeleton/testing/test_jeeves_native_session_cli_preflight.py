"""Pure first-laptop resource admission tests; no real model is loaded."""
from __future__ import annotations

from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest import mock
import unittest

from skeleton.jeeves.agent.native_operator_preflight import (
    NativeOperatorHold,
    check_native_resource_shape,
    check_operator_admission,
)
from skeleton.jeeves.agent.native_operator_session_cli import main as session_main


def resource(**overrides):
    options = dict(
        context_tokens=4096,
        output_tokens=1024,
        native_threads=4,
        gpu_layers=0,
        capacity_budget_bytes=8000000000,
    )
    options.update(overrides)
    return check_native_resource_shape(**options)


def cli_args(*extra):
    return [
        "--model-root", "/private/approved-model",
        "--state-dir", "/private/isolated-state",
        "--tenant", "local",
        "--subject", "operator",
        "--approve-native", "--commands-stdin",
        *extra,
    ]


def must_hold_before_activate(*extra):
    stdin = mock.Mock()
    stderr = StringIO()
    with (
        mock.patch(
            "skeleton.jeeves.agent.native_operator_session_cli.activate_checked"
        ) as activate,
        mock.patch(
            "skeleton.jeeves.agent.native_operator_session_cli.sys.stdin",
            stdin,
        ),
        redirect_stderr(stderr),
    ):
        result = session_main(cli_args(*extra))
    activate.assert_not_called()
    stdin.buffer.read.assert_not_called()
    stdin.buffer.readline.assert_not_called()
    return result, stderr.getvalue()


class TestSessionCliAdmission(unittest.TestCase):
    def test_rejects_bad_context_before_source_bootstrap(self):
        for value in ("0","64","127","131073"):
            with self.subTest(context=value):
                result,error = must_hold_before_activate("--context",value)
                self.assertEqual(result,2)
                self.assertNotIn(value+" model",error)

    def test_rejects_generation_ceiling_not_below_context(self):
        for args in (
            ("--context","1024","--max-output-tokens","1024"),
            ("--context","512","--max-output-tokens","1024"),
            ("--max-output-tokens","8193"),
            ("--max-output-tokens","0"),
        ):
            with self.subTest(args=args):
                result,error = must_hold_before_activate(*args)
                self.assertEqual(result,2)
                self.assertIn('"status": "held"',error)

    def test_invalid_threads_and_gpu_offload_never_start_worker(self):
        for args in (
            ("--threads","0"),("--threads","65"),
            ("--threads","-1"),("--gpu-layers","-1"),
            ("--gpu-layers","129"),("--capacity-budget-bytes","0"),
            ("--capacity-budget-bytes","20000000001"),
        ):
            with self.subTest(args=args):
                result,_=must_hold_before_activate(*args)
                self.assertEqual(result,2)

    def test_untrusted_capacity_directory_rejected_before_open(self):
        for invalid in ("relative/storage","/private/../outside"):
            with self.subTest(invalid=invalid):
                result,error = must_hold_before_activate(
                    "--capacity-root",invalid
                )
                self.assertEqual(result,2)
                self.assertNotIn(invalid,error)

    def test_invalid_principal_denied_before_native_initialization(self):
        for args in (
            ("--tenant","invalid/tenant"),
            ("--subject","operator\x00bad"),
        ):
            # Add argparse duplicates; the later value is the one admitted.
            with self.subTest(args=args):
                result,_=must_hold_before_activate(*args)
                self.assertEqual(result,2)

    def test_missing_explicit_operator_approval_holds(self):
        original=cli_args()
        for flag in ("--approve-native","--commands-stdin"):
            args=[part for part in original if part!=flag]
            stderr=StringIO()
            with (
                mock.patch(
                    "skeleton.jeeves.agent.native_operator_session_cli.activate_checked"
                ) as activate,
                redirect_stderr(stderr),
            ):
                code=session_main(args)
            self.assertEqual(code,2)
            activate.assert_not_called()
            self.assertIn('"status": "held"',stderr.getvalue())

if __name__ == "__main__":
    unittest.main()
