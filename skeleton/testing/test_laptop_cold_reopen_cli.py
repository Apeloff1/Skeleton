"""Operator approval and data-custody CLI checks for native cold reopen.

This test never starts a real local model, installs source bytes or qualifies
Windows, GPU, WSL2, laptop hardware or release. It verifies that the command
delegates to the existing source-bound activation twice, never itself.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import BytesIO, StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import json
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime.cli import main
from skeleton.testing.laptop_runtime_test_support import FakeWorker, MODEL, TOKENIZER


def command(*extras):
    return [
        "--model-root","/private/approved-gguf",
        "--state-dir","/private/sqlite",
        "--tenant","local","--subject","owner",
        "--mode","cold-reopen","--prompt-stdin",
        *extras,
    ]


def _synthetic_approval(kwargs, report):
    # Source-only double: the publisher must run while a worker is supplied.
    kwargs["publisher"](FakeWorker(), object(), dict(report))
    return dict(report)


def invoke(args,*,payload=b"  private multiline task\r\n"):
    reader=SimpleNamespace(buffer=BytesIO(payload))
    stdout=StringIO()
    stderr=StringIO()
    report={
        "schema":"laptop-native-cold-reopen-e2e.v1",
        "model_sha256":"a"*64,
        "tokenizer_sha256":"b"*64,
        "output_sha256":"c"*64,
        "source_verified_twice":True,
        "sqlite_replay_after_cold_reopen":True,
        "second_generation_attempted":False,
        "private_prompt_disclosed":False,
        "physical_device_qualified":False,
        "release_certified":False,
    }
    with (
        mock.patch(
            "skeleton.ai.runtime.operational_ai.laptop_runtime.cli.sys.stdin",
            reader,
        ),
        mock.patch(
            "skeleton.ai.runtime.operational_ai.laptop_runtime.cli.activate_checked"
        ) as single_activation,
        mock.patch(
            "skeleton.ai.runtime.operational_ai.laptop_runtime.source_guard.require_activated_source",
            return_value={
                "model_sha256":MODEL,"tokenizer_sha256":TOKENIZER,
                "manifest_sha256":"c"*64,"archive_sha256":"d"*64,
                "source_sha":"e"*40,"installed_model_bytes":2048,
                "installed_shard_count":1,
            },
        ),
        mock.patch(
            "skeleton.ai.runtime.operational_ai.laptop_runtime.cli.run_cold_reopen_acceptance",
            side_effect=lambda **kwargs:_synthetic_approval(kwargs,report),
        ) as qualify,
        redirect_stdout(stdout),redirect_stderr(stderr),
    ):
        status=main(args)
    return status,stdout.getvalue(),stderr.getvalue(),reader,single_activation,qualify


class ColdReopenOperatorCLITests(unittest.TestCase):
    def test_two_native_activations_require_explicit_operator_approval(self):
        status,out,err,reader,activated,qualified=invoke(command())
        self.assertEqual(status,2)
        self.assertEqual(out,"")
        self.assertEqual(reader.buffer.tell(),0)
        activated.assert_not_called()
        qualified.assert_not_called()

    def test_approved_operator_cli_preserves_private_prompt_bytes(self):
        private=b"  write a function:\r\n    return 42\r\n"
        status,out,err,reader,activated,qualified=invoke(
            command("--approve-real-acceptance"),payload=private,
        )
        self.assertEqual(status,0,err)
        self.assertFalse(err)
        activated.assert_not_called()
        qualified.assert_called_once()
        kw=qualified.call_args.kwargs
        self.assertEqual(kw["prompt"].encode(),private)
        self.assertEqual(kw["model_root"],Path("/private/approved-gguf"))
        self.assertEqual(kw["state_dir"],Path("/private/sqlite"))
        self.assertIs(kw["approved"],True)
        report=json.loads(out)
        self.assertEqual(report["status"],"native-cold-reopen-sqlite-verified")
        self.assertFalse(report["release_certified"])
        self.assertNotIn("write a function",out)

    def test_stale_request_ids_are_rejected_before_input_or_installer(self):
        for extra in (
            ("--session","previous_session"),
            ("--request-id","previous_request"),
        ):
            with self.subTest(extra=extra):
                status,out,err,reader,activated,qualified=invoke(
                    command("--approve-real-acceptance",*extra),
                )
                self.assertEqual(status,2)
                self.assertEqual(reader.buffer.tell(),0)
                activated.assert_not_called()
                qualified.assert_not_called()

    def test_impossible_native_shape_rejected_before_stdin(self):
        for extra in (
            ("--context","127"),
            ("--context","128","--max-new-tokens","128"),
            ("--threads","0"),
            ("--gpu-layers","129"),
            ("--capacity-slots","0"),
        ):
            with self.subTest(extra=extra):
                status,out,err,reader,activated,qualified=invoke(
                    command("--approve-real-acceptance",*extra),
                )
                self.assertEqual(status,2)
                self.assertEqual(reader.buffer.tell(),0)
                activated.assert_not_called()
                qualified.assert_not_called()

    def test_invalid_private_utf8_is_not_forwarded_to_native_loader(self):
        for payload in (b"",b" \r\n",b"bad\x00prompt",b"broken\xff",b"a"*32769):
            with self.subTest(size=len(payload)):
                status,out,err,reader,activated,qualified=invoke(
                    command("--approve-real-acceptance"),payload=payload,
                )
                self.assertEqual(status,2)
                self.assertFalse(out)
                activated.assert_not_called()
                qualified.assert_not_called()
                self.assertNotIn("bad",err)

    def test_rejected_source_or_sqlite_reopen_never_emits_success(self):
        status=None
        stderr=StringIO()
        stdout=StringIO()
        reader=SimpleNamespace(buffer=BytesIO(b"private prompt"))
        from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
        with (
            mock.patch(
                "skeleton.ai.runtime.operational_ai.laptop_runtime.cli.sys.stdin",reader,
            ),
            mock.patch(
                "skeleton.ai.runtime.operational_ai.laptop_runtime.cli.run_cold_reopen_acceptance",
                side_effect=ContractViolation("private source receipt missing"),
            ),
            redirect_stdout(stdout),redirect_stderr(stderr),
        ):
            status=main(command("--approve-real-acceptance"))
        self.assertEqual(status,2)
        self.assertFalse(stdout.getvalue())
        self.assertIn('"status": "held"',stderr.getvalue())
        self.assertNotIn("private source",stderr.getvalue())

if __name__=="__main__":
    unittest.main()
