"""Native Jeeves single-shot stdout is bounded and nonretrying.

All workers, GGUF generation, installed rights and stream failures are
synthetic. A source-only pass does not prove laptop/device/Windows readiness.
"""
from __future__ import annotations

from contextlib import nullcontext
from io import BytesIO, StringIO
from types import SimpleNamespace
from unittest import mock
import json
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
from skeleton.jeeves.agent.native_cli import (
    _publish_native_record, main as cli_main,
)
from skeleton.testing.laptop_runtime_test_support import FakeWorker, MODEL, TOKENIZER

SOURCE = {
    "model_sha256": MODEL, "tokenizer_sha256": TOKENIZER,
    "manifest_sha256": "c" * 64, "archive_sha256": "d" * 64,
    "source_sha": "e" * 40, "installed_model_bytes": 2048,
    "installed_shard_count": 1,
}


class ShortWriter(StringIO):
    def __init__(self, count):
        super().__init__()
        self.count = count
    def write(self, value):
        if type(self.count) is int and self.count > 0:
            super().write(value[:self.count])
        return self.count


class BadFlush(StringIO):
    def flush(self):
        raise OSError("private fixture stream failed to flush")


class OutputFenceTests(unittest.TestCase):
    def setUp(self):
        self.worker = FakeWorker()
        self.fence = mock.Mock()
        self.fence.assert_live.return_value = None

    def publish(self, payload, writer=None, **kwargs):
        out = StringIO() if writer is None else writer
        with mock.patch(
            "skeleton.jeeves.agent.native_cli.sys.stdout", out
        ):
            _publish_native_record(
                self.worker, self.fence, payload, **kwargs,
            )
        return out

    def test_finite_json_result_success_is_one_complete_line(self):
        out = self.publish({"status": "ok", "release_certified": False})
        self.assertEqual(len(out.getvalue().splitlines()), 1)
        self.assertEqual(json.loads(out.getvalue())["status"], "ok")
        self.fence.assert_live.assert_called_once_with(self.worker)

    def test_unicode_byte_ceiling_not_character_ceiling(self):
        payload={"answer":"🦊"*4}
        expected=json.dumps(payload,sort_keys=True,ensure_ascii=False)+"\n"
        exact=len(expected.encode("utf-8"))
        self.assertEqual(
            self.publish(payload, maximum_bytes=exact).getvalue(), expected
        )
        self.fence.reset_mock()
        target=StringIO()
        with self.assertRaises(ValueError), mock.patch(
            "skeleton.jeeves.agent.native_cli.sys.stdout", target
        ):
            _publish_native_record(
                self.worker,self.fence,payload,maximum_bytes=exact-1
            )
        self.assertFalse(target.getvalue())
        self.fence.assert_not_called()

    def test_large_private_result_denied_before_output(self):
        target=StringIO()
        with mock.patch(
            "skeleton.jeeves.agent.native_cli.sys.stdout", target
        ):
            with self.assertRaisesRegex(ValueError, "disclosure bound"):
                _publish_native_record(
                    self.worker,self.fence,{"answer":"SECRET"*300000},
                )
        self.assertFalse(target.getvalue())
        self.fence.assert_not_called()

    def test_source_revocation_blocks_any_private_byte(self):
        target=StringIO()
        self.fence.assert_live.side_effect=ContractViolation("lease lost")
        with mock.patch(
            "skeleton.jeeves.agent.native_cli.sys.stdout", target
        ):
            with self.assertRaises(ContractViolation):
                _publish_native_record(
                    self.worker,self.fence,{"answer":"private source content"},
                )
        self.assertFalse(target.getvalue())

    def test_partial_or_noninteger_write_never_looks_successful(self):
        for count in (0,1,True,None,-1,1.1,"all"):
            with self.subTest(count=repr(count)):
                output=ShortWriter(count)
                with mock.patch(
                    "skeleton.jeeves.agent.native_cli.sys.stdout", output
                ):
                    with self.assertRaises(OSError):
                        _publish_native_record(
                            self.worker,self.fence,{"answer":"private"},
                        )

    def test_failed_flush_is_terminal(self):
        with mock.patch(
            "skeleton.jeeves.agent.native_cli.sys.stdout", BadFlush()
        ):
            with self.assertRaises(OSError):
                _publish_native_record(self.worker,self.fence,{"status":"ok"})

    def test_nan_or_nonobject_never_reaches_stdout(self):
        for payload in (True,[],None,{"status":float("nan")}):
            output=StringIO()
            with self.subTest(value=repr(payload)),mock.patch(
                "skeleton.jeeves.agent.native_cli.sys.stdout",output
            ):
                with self.assertRaises((ValueError,TypeError)):
                    _publish_native_record(self.worker,self.fence,payload)
            self.assertFalse(output.getvalue())

    def test_invalid_byte_ceiling_is_not_a_lease(self):
        for limit in (None,True,0,1048577,1.5,"100"):
            target=StringIO()
            with self.subTest(limit=repr(limit)),mock.patch(
                "skeleton.jeeves.agent.native_cli.sys.stdout",target
            ):
                with self.assertRaises(ValueError):
                    _publish_native_record(
                        self.worker,self.fence,{"status":"ok"},
                        maximum_bytes=limit,
                    )
            self.assertFalse(target.getvalue())

    def test_single_chat_short_write_returns_hold_without_second_generation(self):
        worker=FakeWorker()
        chat=mock.Mock()
        chat.turn.return_value.to_record.return_value={"answer":"private"}
        source=SimpleNamespace(buffer=BytesIO(b"test user prompt"))
        out=ShortWriter(3)
        err=StringIO()
        args=[
            "--model-root","/private/model","--state-dir","/private/sqlite",
            "--tenant","local","--subject","owner",
            "--mode","chat","--task-stdin",
        ]
        with (
            mock.patch(
                "skeleton.jeeves.agent.native_cli.activate_checked",
                return_value=(nullcontext(),worker,object()),
            ),
            mock.patch(
                "skeleton.jeeves.agent.native_cli.inspect_native_jeeves",
                return_value=SimpleNamespace(source_bridge_ready=True),
            ),
            mock.patch(
                "skeleton.jeeves.agent.native_source_fence.require_activated_source",
                return_value=dict(SOURCE),
            ),
            mock.patch(
                "skeleton.jeeves.agent.native_cli.NativeJeevesChat",
                return_value=chat,
            ),
            mock.patch("skeleton.jeeves.agent.native_cli.sys.stdin",source),
            mock.patch("skeleton.jeeves.agent.native_cli.sys.stdout",out),
            mock.patch("skeleton.jeeves.agent.native_cli.sys.stderr",err),
        ):
            code=cli_main(args)
        self.assertEqual(code,2)
        self.assertEqual(len(out.getvalue()),3)
        self.assertNotIn("test user prompt",err.getvalue())
        self.assertIn('"status": "held"',err.getvalue())
        chat.turn.assert_called_once()
        self.assertEqual(worker.generation_calls,0)


if __name__=="__main__":
    unittest.main()
