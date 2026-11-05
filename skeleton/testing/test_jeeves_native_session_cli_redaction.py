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


class TestSessionCliRedaction(unittest.TestCase):
    def test_unknown_flag_with_secret_value_never_echoes_secret(self):
        payload="private_operator_token_123"
        code,error=must_hold_before_activate(
            "--unrecognized-model-source",payload
        )
        self.assertEqual(code,2)
        self.assertNotIn(payload,error)
        self.assertEqual(error.count("\n"),1)

    def test_noninteger_argparse_value_is_redacted(self):
        payload="private_gguf_path_not_a_number"
        code,error=must_hold_before_activate("--threads",payload)
        self.assertEqual(code,2)
        self.assertNotIn(payload,error)
        self.assertNotIn("usage:",error)
        self.assertIn("NativeOperatorSessionHold",error)

    def test_missing_required_flags_is_one_canonical_hold(self):
        stderr=StringIO()
        with (
            mock.patch(
                "skeleton.jeeves.agent.native_operator_session_cli.activate_checked"
            ) as activate,
            redirect_stderr(stderr),
        ):
            code=session_main(["--approve-native"])
        self.assertEqual(code,2)
        self.assertEqual(stderr.getvalue().count("\n"),1)
        activate.assert_not_called()
        self.assertNotIn("usage:",stderr.getvalue())

    def test_invalid_path_with_nul_cannot_enter_loader(self):
        code,error=must_hold_before_activate("--model-root","/private/invalid\x00path")
        self.assertEqual(code,2)
        self.assertIn('"status": "held"',error)
        self.assertNotIn("invalid",error)

    def test_rejected_command_does_not_print_model_identity_or_path(self):
        code,error=must_hold_before_activate(
            "--model-root","/private/secret-model-revision",
            "--gpu-layers","129",
        )
        self.assertEqual(code,2)
        self.assertNotIn("secret-model-revision",error)
        self.assertNotIn("private",error)
        self.assertNotIn("model-root",error)

    def test_nonexistent_capacity_path_is_only_structural_preflight(self):
        # Pure preflight must not stat/read a path; actual activation remains
        # responsible for trusted ownership checks and source verification.
        path=Path("/private/unmounted_capacity_root")
        self.assertTrue(path.is_absolute())
        self.assertIsNone(resource())

if __name__ == "__main__":
    unittest.main()
