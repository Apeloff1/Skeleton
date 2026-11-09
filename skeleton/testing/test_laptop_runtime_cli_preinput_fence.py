"""Finite native request admission before any private I/O or GGUF process.

The simulated tests cannot prove a real installed model, device, Windows,
WSL2, source-rights approval or release readiness.
"""
from __future__ import annotations

from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest import mock
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
from skeleton.ai.runtime.operational_ai.laptop_runtime.preflight import validate_native_shape
from skeleton.ai.runtime.operational_ai.laptop_runtime.cli import main as laptop_main
from skeleton.ai.runtime.operational_ai.laptop_runtime.client_cli import main as client_main
from skeleton.ai.runtime.operational_ai.laptop_runtime.cli_doctor import main as doctor_main

class TestLocalCliPreInputFence(unittest.TestCase):
    @staticmethod
    def args(*rest):
        return ["--model-root","/private/installed",
                "--state-dir","/private/local-sqlite",
                "--tenant","local","--subject","operator",
                "--mode","once","--prompt-stdin",*rest]

    def test_impossible_native_budgets_are_held_without_reading_stdin(self):
        for switches in (
            ("--context","0"),
            ("--context","128","--max-new-tokens","128"),
            ("--max-new-tokens","0"),
            ("--threads","65"),
            ("--gpu-layers","-1"),
            ("--capacity-slots","0"),
            ("--capacity-budget-bytes","0"),
        ):
            with self.subTest(switches=switches):
                stdin=mock.Mock()
                err=StringIO()
                with (
                    mock.patch("skeleton.ai.runtime.operational_ai.laptop_runtime.cli.sys.stdin",stdin),
                    mock.patch("skeleton.ai.runtime.operational_ai.laptop_runtime.cli.activate_checked") as activate,
                    redirect_stderr(err),
                ):
                    code=laptop_main(self.args(*switches))
                self.assertEqual(code,2)
                stdin.buffer.read.assert_not_called()
                activate.assert_not_called()
                self.assertNotIn("/private",err.getvalue())

    def test_invalid_private_path_denied_before_prompt_and_model(self):
        for args in (
            ("--model-root","relative/model"),
            ("--state-dir","/private/../elsewhere"),
            ("--capacity-root","relative/storage"),
        ):
            with self.subTest(args=args):
                stdin=mock.Mock()
                with (
                    mock.patch("skeleton.ai.runtime.operational_ai.laptop_runtime.cli.sys.stdin",stdin),
                    mock.patch("skeleton.ai.runtime.operational_ai.laptop_runtime.cli.activate_checked") as activate,
                    redirect_stderr(StringIO()),
                ):
                    self.assertEqual(laptop_main(self.args(*args)),2)
                stdin.buffer.read.assert_not_called()
                activate.assert_not_called()

    def test_unexpected_or_secret_argparse_value_not_disclosed(self):
        secret="private-model-authentication-value"
        for switches in (("--unknown",secret),("--threads",secret)):
            with self.subTest(switches=switches):
                stderr=StringIO()
                with (
                    mock.patch("skeleton.ai.runtime.operational_ai.laptop_runtime.cli.activate_checked") as activate,
                    redirect_stderr(stderr),
                ):
                    self.assertEqual(laptop_main(self.args(*switches)),2)
                activate.assert_not_called()
                self.assertNotIn(secret,stderr.getvalue())
                self.assertNotIn("usage:",stderr.getvalue())

    def test_noncanonical_port_denied_before_native_worker(self):
        for port in ("0","65536","-1"):
            with self.subTest(port=port):
                with (
                    mock.patch("skeleton.ai.runtime.operational_ai.laptop_runtime.cli.activate_checked") as activate,
                    redirect_stderr(StringIO()),
                ):
                    self.assertEqual(laptop_main(self.args("--port",port)),2)
                activate.assert_not_called()

if __name__=="__main__":
    unittest.main()
