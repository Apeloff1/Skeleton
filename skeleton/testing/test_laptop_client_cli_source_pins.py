"""CLI-installed model pins and strict private-task input admission.

Pure source test: no model weights, external connection, device qualification
or release approval. Real native worker and socket remain separate contracts.
"""
from __future__ import annotations

from contextlib import redirect_stdout, redirect_stderr
from io import BytesIO, StringIO
from types import SimpleNamespace
from unittest import mock
import os
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime.client_cli import main as client_main
from skeleton.testing.laptop_runtime_test_support import MODEL, TOKENIZER


def argv(action="turn", *extras):
    head=["--action",action]
    if action in ("turn","replay"):
        head += ["--session","s_private","--stdin-prompt"]
    return head+list(extras)


def call_cli(options, *, raw=b"  exact code block\n", env=None):
    stdin=SimpleNamespace(buffer=BytesIO(raw))
    output=StringIO()
    errors=StringIO()
    network=mock.Mock()
    network.turn.return_value={"receipt":{"text":"test-only"}}
    network.replay.return_value={"replay":None,"found":False}
    network.history.return_value={"session_id":"s_private","messages":[]}
    network.create.return_value={"session_id":"s_created"}
    network.request.return_value={"status":"simulated"}
    network.identity.return_value={"model_sha256":MODEL}
    environment={"SKELETON_LOCAL_AI_BEARER":"x"*64}
    if env:environment.update(env)
    with (
        mock.patch(
            "skeleton.ai.runtime.operational_ai.laptop_runtime.client_cli.LaptopClient",
            return_value=network,
        ) as built,
        mock.patch.dict(os.environ,environment,clear=True),
        mock.patch(
            "skeleton.ai.runtime.operational_ai.laptop_runtime.client_cli.sys.stdin",
            stdin,
        ),
        redirect_stdout(output),
        redirect_stderr(errors),
    ):
        status=client_main(options)
    return status,output.getvalue(),errors.getvalue(),network,built,stdin


class ClientCLIModelPins(unittest.TestCase):
    def test_exact_explicit_installed_model_and_tokenizer_are_forwarded(self):
        args=argv("turn","--request-id","r_1",
                  "--expected-model-sha256",MODEL,
                  "--expected-tokenizer-sha256",TOKENIZER)
        status,out,err,client,built,stdin=call_cli(args)
        self.assertEqual(status,0,err)
        self.assertFalse(err)
        self.assertIn('"status": "ok"',out)
        built.assert_called_once_with(
            port=8765,bearer="x"*64,
            expected_model_sha256=MODEL,
            expected_tokenizer_sha256=TOKENIZER,
        )
        client.turn.assert_called_once_with(
            "s_private","r_1","  exact code block\n",
        )

    def test_two_installed_source_pins_must_be_provided_together(self):
        for options in (
            ["--expected-model-sha256",MODEL],
            ["--expected-tokenizer-sha256",TOKENIZER],
        ):
            with self.subTest(options=options):
                status,out,err,client,built,stdin=call_cli(
                    argv("turn",*options),
                )
                self.assertEqual(status,2)
                self.assertFalse(out)
                built.assert_not_called()
                self.assertIn('"status": "held"',err)

    def test_invalid_source_digest_fails_before_private_stdin_read(self):
        for digest in ("invalid","F"*64,"0"*63,"", "a/b"):
            with self.subTest(digest=digest):
                args=argv("turn","--expected-model-sha256",digest,
                          "--expected-tokenizer-sha256",TOKENIZER)
                status,out,err,client,built,stdin=call_cli(args)
                self.assertEqual(status,2)
                built.assert_not_called()
                self.assertEqual(stdin.buffer.tell(),0)

    def test_model_pins_may_be_supplied_by_operator_environment(self):
        status,out,err,client,built,stdin=call_cli(
            argv("status"),env={
                "SKELETON_LOCAL_AI_MODEL_SHA256":MODEL,
                "SKELETON_LOCAL_AI_TOKENIZER_SHA256":TOKENIZER,
            },
        )
        self.assertEqual(status,0,err)
        built.assert_called_once_with(
            port=8765,bearer="x"*64,
            expected_model_sha256=MODEL,
            expected_tokenizer_sha256=TOKENIZER,
        )
        self.assertEqual(client.identity.call_count,2)
        client.request.assert_called_once_with("status",{})

    def test_explicit_flags_override_environment_pair(self):
        status,out,err,client,built,stdin=call_cli(
            argv("create","--expected-model-sha256",MODEL,
                 "--expected-tokenizer-sha256",TOKENIZER),
            env={
                "SKELETON_LOCAL_AI_MODEL_SHA256":"e"*64,
                "SKELETON_LOCAL_AI_TOKENIZER_SHA256":"f"*64,
            },
        )
        self.assertEqual(status,0,err)
        self.assertEqual(built.call_args.kwargs["expected_model_sha256"],MODEL)
        client.create.assert_called_once_with()

    def test_missing_replay_id_denied_without_reading_private_prompt(self):
        status,out,err,client,built,stdin=call_cli(argv("replay"))
        self.assertEqual(status,2)
        self.assertEqual(stdin.buffer.tell(),0)
        client.replay.assert_not_called()
        self.assertFalse(out)

    def test_invalid_request_id_denied_before_private_stdin(self):
        status,out,err,client,built,stdin=call_cli(
            argv("turn","--request-id","invalid/request"),
        )
        self.assertEqual(status,2)
        self.assertEqual(stdin.buffer.tell(),0)
        client.turn.assert_not_called()

    def test_status_uses_two_source_epochs_without_native_generation(self):
        status,out,err,client,built,stdin=call_cli(argv("status"))
        self.assertEqual(status,0,err)
        self.assertEqual(client.identity.call_count,2)
        client.turn.assert_not_called()
        client.replay.assert_not_called()
        self.assertEqual(stdin.buffer.tell(),0)


if __name__=="__main__":
    unittest.main()
