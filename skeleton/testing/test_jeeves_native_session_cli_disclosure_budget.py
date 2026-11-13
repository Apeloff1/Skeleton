"""Admission of native operator output caps before weights or private stdin.

This file patches startup; no real GGUF or device is exercised.
"""
from __future__ import annotations

from contextlib import redirect_stderr
from io import StringIO
from unittest import mock
import unittest

from skeleton.jeeves.agent.native_operator_session_cli import main


def args(*extra):
    return [
        "--model-root","/private/model",
        "--state-dir","/private/sqlite",
        "--tenant","local","--subject","owner",
        "--approve-native","--commands-stdin",
        *extra,
    ]


class OperatorResultBudgetCLIAdmissionTests(unittest.TestCase):
    def test_bad_result_caps_never_inspect_or_activate_gguf(self):
        for extra in (
            ("--maximum-result-bytes","0"),
            ("--maximum-result-bytes","1048577"),
            ("--maximum-session-result-bytes","0"),
            ("--maximum-session-result-bytes","67108865"),
            ("--maximum-session-result-bytes","100"),
            ("--maximum-result-bytes","not-an-int"),
        ):
            with self.subTest(extra=extra):
                stderr=StringIO()
                with (
                    mock.patch(
                        "skeleton.jeeves.agent.native_operator_session_cli.activate_checked",
                    ) as activated,
                    mock.patch(
                        "skeleton.jeeves.agent.native_operator_session_cli.sys.stdin",
                    ) as stdin,
                    redirect_stderr(stderr),
                ):
                    result=main(args(*extra))
                self.assertEqual(result,2)
                activated.assert_not_called()
                stdin.buffer.readline.assert_not_called()
                self.assertIn('"status": "held"',stderr.getvalue())
                self.assertNotIn("/private/model",stderr.getvalue())

    def test_well_typed_caps_alone_do_not_grant_native_approval(self):
        with (
            mock.patch(
                "skeleton.jeeves.agent.native_operator_session_cli.activate_checked",
            ) as activated,
            redirect_stderr(StringIO()),
        ):
            result=main([
                "--model-root","/private/model",
                "--state-dir","/private/sqlite",
                "--tenant","local","--subject","owner",
                "--maximum-result-bytes","2048",
                "--maximum-session-result-bytes","16384",
                "--commands-stdin",
            ])
        self.assertEqual(result,2)
        activated.assert_not_called()


if __name__=="__main__":
    unittest.main()
