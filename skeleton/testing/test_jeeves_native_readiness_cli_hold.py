"""Jeeves CLI cannot activate chat or durable terminal on forged GGUF.

The mock worker and self-asserted rights are deliberately untrusted.
Only the real installed inspector can authorize a source-ready bridge.
No real model, physical laptop, rights or release evidence is created.
"""
from __future__ import annotations

from contextlib import nullcontext, redirect_stdout, redirect_stderr
from io import BytesIO, StringIO
from types import SimpleNamespace
from unittest import mock
import json
import unittest

from skeleton.jeeves.agent.native_cli import main as chat_main
from skeleton.jeeves.agent.native_operator_session_cli import main as terminal_main
from skeleton.testing.laptop_runtime_test_support import FakeWorker, MODEL


def args_for_chat():
    return [
        "--model-root","/private/approved-model",
        "--state-dir","/private/state",
        "--tenant","local","--subject","owner",
        "--mode","chat","--task-stdin",
    ]


def args_for_terminal():
    return [
        "--model-root","/private/approved-model",
        "--state-dir","/private/state",
        "--tenant","local","--subject","owner",
        "--approve-native","--commands-stdin",
    ]


class TestJeevesNativeCLIInstalledSourceHold(unittest.TestCase):
    def test_fake_worker_and_forged_installer_cannot_start_chat(self):
        fake=FakeWorker()
        raw=SimpleNamespace(buffer=BytesIO(b"private local question"))
        out,err=StringIO(),StringIO()
        with (
            mock.patch(
                "skeleton.jeeves.agent.native_cli.activate_checked",
                return_value=(nullcontext(),fake,object()),
            ) as activate,
            mock.patch("skeleton.jeeves.agent.native_cli.sys.stdin",raw),
            mock.patch("skeleton.jeeves.agent.native_cli.NativeJeevesChat") as chat,
            redirect_stdout(out),redirect_stderr(err),
        ):
            result=chat_main(args_for_chat())
        self.assertEqual(result,2)
        self.assertEqual(activate.call_count,1)
        chat.assert_not_called()
        self.assertEqual(fake.generation_calls,0)
        self.assertFalse(fake.spine.created)
        self.assertFalse(out.getvalue())
        self.assertNotIn("private local question",err.getvalue())
        self.assertIn('"status": "held"',err.getvalue())

    def test_fake_worker_and_forged_installer_cannot_start_operator_stream(self):
        fake=FakeWorker()
        reader=SimpleNamespace(buffer=BytesIO(
            b'{"schema":"jeeves.native_operator_command.v1","operation":"status"}\n'
        ))
        out,err=StringIO(),StringIO()
        with (
            mock.patch(
                "skeleton.jeeves.agent.native_operator_session_cli.activate_checked",
                return_value=(nullcontext(),fake,object()),
            ) as activated,
            mock.patch(
                "skeleton.jeeves.agent.native_operator_session_cli.sys.stdin",
                reader,
            ),
            mock.patch(
                "skeleton.jeeves.agent.native_operator_session_cli.NativeOperatorSession"
            ) as terminal,
            redirect_stdout(out),redirect_stderr(err),
        ):
            result=terminal_main(args_for_terminal())
        self.assertEqual(result,2)
        self.assertEqual(activated.call_count,1)
        terminal.assert_not_called()
        self.assertEqual(reader.buffer.tell(),0)
        self.assertEqual(fake.generation_calls,0)
        self.assertFalse(fake.spine.created)
        self.assertFalse(out.getvalue())
        self.assertIn('"status": "held"',err.getvalue())

    def test_malformed_fake_native_source_does_not_expose_private_model_result(self):
        fake=FakeWorker()
        fake.spine.backend.model_digest="f"*64
        reader=SimpleNamespace(buffer=BytesIO(b"private operator task"))
        out,err=StringIO(),StringIO()
        with (
            mock.patch(
                "skeleton.jeeves.agent.native_cli.activate_checked",
                return_value=(nullcontext(),fake,object()),
            ),
            mock.patch("skeleton.jeeves.agent.native_cli.sys.stdin",reader),
            redirect_stdout(out),redirect_stderr(err),
        ):
            code=chat_main(args_for_chat())
        self.assertEqual(code,2)
        self.assertNotIn("private",out.getvalue())
        self.assertNotIn("private operator task",err.getvalue())
        self.assertEqual(fake.generation_calls,0)


if __name__=="__main__":
    unittest.main()
