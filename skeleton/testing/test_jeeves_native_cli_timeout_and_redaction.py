"""Jeeves native operator CLI exact-task admission and source identity.

The installed GGUF and native token generator are deliberately patched out.
These tests do not qualify source rights, real inference, physical laptop
hardware, Windows/WSL2 or release.
"""
from __future__ import annotations

from contextlib import nullcontext, redirect_stderr, redirect_stdout
from io import BytesIO, StringIO
from types import SimpleNamespace
from unittest import mock
import json
import unittest

from skeleton.jeeves.agent.native_cli import main as jeeves_main
from skeleton.jeeves.agent.native_operator_preflight import (
    NativeOperatorHold, check_operator_admission, check_native_resource_shape,
)
from skeleton.testing.laptop_runtime_test_support import FakeWorker, MODEL, TOKENIZER


def cli_args(*extra):
    return [
        "--model-root", "/private/approved-gguf",
        "--state-dir", "/private/sqlite",
        "--tenant", "local", "--subject", "owner",
        "--mode", "chat", "--task-stdin", *extra,
    ]


def call_cli(argv, *, prompt=b"  exact user prompt \r\n", worker=None):
    w = worker or FakeWorker()
    reader = SimpleNamespace(buffer=BytesIO(prompt))
    out = StringIO()
    err = StringIO()
    chat = mock.Mock()
    chat.turn.return_value.to_record.return_value = {
        "text": "synthetic answer",
        "output_sha256": "c" * 64,
    }
    with (
        mock.patch("skeleton.jeeves.agent.native_cli.sys.stdin", reader),
        mock.patch(
            "skeleton.jeeves.agent.native_cli.activate_checked",
            return_value=(nullcontext(), w, object()),
        ) as activated,
        mock.patch(
            "skeleton.jeeves.agent.native_cli.inspect_native_jeeves",
            return_value=SimpleNamespace(source_bridge_ready=True),
        ),
        mock.patch(
            "skeleton.jeeves.agent.native_source_fence.require_activated_source",
            return_value={
                "model_sha256":MODEL,"tokenizer_sha256":TOKENIZER,
                "manifest_sha256":"c"*64,"archive_sha256":"d"*64,
                "source_sha":"e"*40,"installed_model_bytes":1024,
                "installed_shard_count":1,
            },
        ),
        mock.patch(
            "skeleton.jeeves.agent.native_cli.NativeJeevesChat",
            return_value=chat,
        ),
        redirect_stdout(out), redirect_stderr(err),
    ):
        code = jeeves_main(argv)
    return code, out.getvalue(), err.getvalue(), reader, w, activated, chat


class JeevesNativeCliBounds(unittest.TestCase):
    def test_exact_indented_crlf_task_retained_in_native_chat(self):
        prompt = b"    def local_task():\r\n        return 42\r\n"
        code, out, err, reader, worker, activated, chat = call_cli(
            cli_args("--inference-ms", "43000"), prompt=prompt,
        )
        self.assertEqual(code, 0, err)
        self.assertFalse(err)
        self.assertEqual(activated.call_count, 1)
        self.assertEqual(activated.call_args.kwargs["inference_ms"], 43000)
        chat.turn.assert_called_once_with(prompt.decode("utf8"), request_id=None)
        self.assertNotIn("def local_task", out)
        self.assertFalse(json.loads(out)["release_certified"] if
            "release_certified" in json.loads(out) else False)

    def test_private_unknown_option_never_reaches_argparse_usage(self):
        secret = "private-operator-token-never-echo"
        code, out, err, reader, worker, activated, chat = call_cli(
            cli_args("--invalid-private-flag", secret),
        )
        self.assertEqual(code, 2)
        self.assertFalse(out)
        self.assertIn('"status": "held"', err)
        self.assertNotIn(secret, err)
        self.assertNotIn("usage:", err)
        self.assertEqual(reader.buffer.tell(), 0)
        activated.assert_not_called()
        chat.turn.assert_not_called()

    def test_invalid_operator_root_denied_before_private_stdin(self):
        for flag, path in (
            ("--model-root", "relative/model"),
            ("--state-dir", "/private/../escape"),
            ("--capacity-root", "relative/storage"),
        ):
            with self.subTest(flag=flag, path=path):
                code, out, err, reader, worker, activated, chat = call_cli(
                    cli_args(flag, path),
                )
                self.assertEqual(code, 2)
                self.assertEqual(reader.buffer.tell(), 0)
                activated.assert_not_called()
                self.assertNotIn(path, err)

    def test_invalid_tenant_and_subject_denied_before_task(self):
        for flag, value in (
            ("--tenant", "foreign/tenant"),
            ("--subject", "operator with spaces"),
        ):
            code, out, err, reader, worker, activated, chat = call_cli(
                cli_args(flag, value),
            )
            self.assertEqual(code, 2)
            self.assertEqual(reader.buffer.tell(), 0)
            activated.assert_not_called()

    def test_invalid_inference_timeout_denied_before_stdin_and_gguf(self):
        for value in ("0", "1", "99", "600001", "-1", "NaN"):
            with self.subTest(timeout=value):
                code, out, err, reader, worker, activated, chat = call_cli(
                    cli_args("--inference-ms", value),
                )
                self.assertEqual(code, 2)
                self.assertEqual(reader.buffer.tell(), 0)
                activated.assert_not_called()
                chat.turn.assert_not_called()
                self.assertNotIn("private", err)

    def test_subminimum_deadline_is_not_a_valid_jeeves_model_reservation(self):
        for value in (0, 1, 99, None, True, "90000", 600001):
            with self.subTest(value=repr(value)):
                with self.assertRaises(NativeOperatorHold):
                    check_native_resource_shape(
                        context_tokens=4096,
                        output_tokens=1024,
                        native_threads=4,
                        gpu_layers=0,
                        capacity_budget_bytes=8000000000,
                        inference_ms=value,
                    )

    def test_valid_inference_timeout_is_part_of_typed_operator_admission(self):
        approved = check_operator_admission(
            mode="chat",task_stdin=True,
            session=None,request_id=None,
            source_root=None,signed_source_manifest=None,
            enable_source_tool=False,max_sources=4,
            max_steps=8,max_model_calls=8,max_wall_seconds=180,
            inference_ms=45000,
        )
        self.assertEqual(approved.inference_ms, 45000)
        self.assertFalse(approved.public_receipt()["may_activate_native"])
        self.assertFalse(approved.public_receipt()["release_certified"])

    def test_backend_source_change_after_turn_never_discloses_result(self):
        worker=FakeWorker()
        reader=SimpleNamespace(buffer=BytesIO(b"private question"))
        out,err=StringIO(),StringIO()
        chat=mock.Mock()
        def switch(*args,**kwargs):
            worker.spine.backend.model_digest = "d"*64
            return SimpleNamespace(to_record=lambda:{"answer":"private model text"})
        chat.turn.side_effect=switch
        with (
            mock.patch("skeleton.jeeves.agent.native_cli.sys.stdin",reader),
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
                return_value={
                    "model_sha256":MODEL,"tokenizer_sha256":TOKENIZER,
                    "manifest_sha256":"c"*64,"archive_sha256":"d"*64,
                    "source_sha":"e"*40,"installed_model_bytes":1024,
                    "installed_shard_count":1,
                },
            ),
            mock.patch(
                "skeleton.jeeves.agent.native_cli.NativeJeevesChat",
                return_value=chat,
            ),
            redirect_stdout(out),redirect_stderr(err),
        ):
            result=jeeves_main(cli_args())
        self.assertEqual(result,2)
        self.assertNotIn("private model text",out.getvalue())
        self.assertNotIn("private question",err.getvalue())
        self.assertIn('"status": "held"',err.getvalue())


if __name__=="__main__":
    unittest.main()
