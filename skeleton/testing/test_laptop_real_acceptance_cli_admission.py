"""First laptop acceptance gates with a synthetic native worker only.

These tests never prove real GGUF execution, installed weights, third-party
source rights, Windows/WSL2 device availability or release qualification.
"""
from __future__ import annotations

from contextlib import nullcontext, redirect_stderr, redirect_stdout
from io import BytesIO, StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import json
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime.cli import main as cli_main
from skeleton.ai.runtime.operational_ai.laptop_runtime.first_turn_acceptance import (
    run as run_acceptance,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import (
    ContractViolation,
)
from skeleton.testing.laptop_runtime_test_support import (
    FakeWorker, MODEL, TOKENIZER, OUTPUT_SHA,
)


def cli_args(*extra):
    return [
        "--model-root","/private/approved-gguf",
        "--state-dir","/private/isolated-sqlite",
        "--tenant","local","--subject","operator",
        "--mode","acceptance",
        "--prompt-stdin",
        *extra,
    ]


def invoke(args, *, worker=None, input_data=b"private local AI prompt"):
    """CLI fake installed stack; never bypass source verification in production."""
    fake=FakeWorker() if worker is None else worker
    # Synthetic CLI fixture must model the requested exact principal; the
    # production installed-source fence never accepts a foreign operator.
    fake.spine.identity.subject="operator"
    input_stream=SimpleNamespace(buffer=BytesIO(input_data))
    output=StringIO()
    error=StringIO()
    with (
        mock.patch(
            "skeleton.ai.runtime.operational_ai.laptop_runtime.cli.activate_checked",
            return_value=(nullcontext(),fake,object()),
        ) as activate,
        # Inject a source-shape fixture ONLY inside the unit test so that
        # CLI serialization/negative paths run without installed GGUF bytes.
        # Production source authorization is explicitly exercised by the
        # separate installed-witness rejection test suite.
        mock.patch(
            "skeleton.ai.runtime.operational_ai.laptop_runtime.first_turn_acceptance.require_activated_source",
            return_value={
                "model_sha256": MODEL, "tokenizer_sha256": TOKENIZER,
                "archive_sha256": "c"*64, "source_sha": "d"*40,
                "manifest_sha256": "e"*64,
                "installed_model_bytes": 1024,
                "installed_shard_count": 1,
            },
        ),
        mock.patch(
            "skeleton.ai.runtime.operational_ai.laptop_runtime.source_guard.require_activated_source",
            return_value={
                "model_sha256": MODEL, "tokenizer_sha256": TOKENIZER,
                "archive_sha256": "c"*64, "source_sha": "d"*40,
                "manifest_sha256": "e"*64,
                "installed_model_bytes": 1024,
                "installed_shard_count": 1,
            },
        ),
        mock.patch(
            "skeleton.ai.runtime.operational_ai.laptop_runtime.cli.sys.stdin",
            input_stream,
        ),
        redirect_stdout(output),
        redirect_stderr(error),
    ):
        status=cli_main(args)
    return status,output.getvalue(),error.getvalue(),fake,activate


class FirstTurnCLIAdmissionTests(unittest.TestCase):
    def test_no_approval_does_not_read_private_stdin_or_activate_model(self):
        stdin=mock.Mock()
        with (
            mock.patch(
                "skeleton.ai.runtime.operational_ai.laptop_runtime.cli.sys.stdin",
                stdin,
            ),
            mock.patch(
                "skeleton.ai.runtime.operational_ai.laptop_runtime.cli.activate_checked"
            ) as activate,
            redirect_stderr(StringIO()),
        ):
            result=cli_main(cli_args())
        self.assertEqual(result,2)
        stdin.buffer.read.assert_not_called()
        activate.assert_not_called()

    def test_real_acceptance_explicitly_approved_prints_only_source_hashes(self):
        status,out,err,worker,activate=invoke(
            cli_args("--approve-real-acceptance"),
            input_data=b"private acceptance prompt marker",
        )
        self.assertEqual(status,0,err)
        self.assertFalse(err)
        self.assertEqual(activate.call_count,1)
        record=json.loads(out)
        self.assertEqual(record["status"],"real-first-turn-native-replay-checked")
        self.assertEqual(record["evidence"]["model_sha256"],MODEL)
        self.assertEqual(record["evidence"]["tokenizer_sha256"],TOKENIZER)
        self.assertEqual(record["evidence"]["output_sha256"],OUTPUT_SHA)
        self.assertGreater(record["evidence"]["generated_tokens"],0)
        self.assertIs(record["evidence"]["replayed_without_generation"],True)
        self.assertIs(record["evidence"]["operator_approved_real_inference"],True)
        self.assertIs(record["evidence"]["device_qualified"],False)
        self.assertIs(record["release_certified"],False)
        self.assertNotIn("private acceptance prompt marker",out)
        self.assertEqual(worker.generation_calls,1)

    def test_approval_is_not_transferable_to_unrelated_cli_modes(self):
        for mode in ("once","serve"):
            with self.subTest(mode=mode):
                args=cli_args("--approve-real-acceptance")
                args[args.index("acceptance")]=mode
                status,out,err,worker,activate=invoke(args)
                self.assertEqual(status,2)
                self.assertFalse(out)
                activate.assert_not_called()
                self.assertEqual(worker.generation_calls,0)

    def test_acceptance_must_allocate_fresh_durable_request(self):
        for item in (("--session","previous_session"),
                     ("--request-id","existing_request")):
            with self.subTest(item=item):
                status,out,err,worker,activate=invoke(
                    cli_args("--approve-real-acceptance",*item)
                )
                self.assertEqual(status,2)
                self.assertFalse(out)
                activate.assert_not_called()
                self.assertEqual(worker.generation_calls,0)

    def test_invalid_resource_budget_held_before_private_prompt_read(self):
        for item in (
            ("--context","0"),("--threads","0"),
            ("--max-new-tokens","4096"),("--capacity-slots","0"),
            ("--gpu-layers","129"),
        ):
            with self.subTest(item=item):
                stdin=mock.Mock()
                with (
                    mock.patch(
                        "skeleton.ai.runtime.operational_ai.laptop_runtime.cli.sys.stdin",
                        stdin,
                    ),
                    mock.patch(
                        "skeleton.ai.runtime.operational_ai.laptop_runtime.cli.activate_checked"
                    ) as activate,
                    redirect_stderr(StringIO()),
                ):
                    result=cli_main(cli_args(
                        "--approve-real-acceptance",*item
                    ))
                self.assertEqual(result,2)
                stdin.buffer.read.assert_not_called()
                activate.assert_not_called()

    def test_explicit_approval_without_stdin_flag_does_not_open_model(self):
        args=cli_args("--approve-real-acceptance")
        args.remove("--prompt-stdin")
        status,out,err,worker,activate=invoke(args)
        self.assertEqual(status,2)
        self.assertFalse(out)
        activate.assert_not_called()
        self.assertEqual(worker.generation_calls,0)

if __name__=="__main__":
    unittest.main()
