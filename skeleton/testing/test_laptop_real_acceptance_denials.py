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
    # Denial tests intentionally reach the native SQLite failure after the
    # synthetic test principal passes *only* the injected source witness.
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


class FirstTurnFailClosedTests(unittest.TestCase):
    def setUp(self):
        self.worker=FakeWorker()

    def test_model_output_without_sqlite_commit_never_yields_acceptance(self):
        original=self.worker.turn
        def uncommitted(*args,**kwargs):
            output=original(*args,**kwargs)
            self.worker.spine.receipts.clear()
            return output
        self.worker.turn=uncommitted
        status,out,err,worker,activate=invoke(
            cli_args("--approve-real-acceptance"),
            worker=self.worker,
        )
        self.assertEqual(status,2)
        self.assertEqual(out,"")
        self.assertIn('"status": "held"',err)
        self.assertNotIn("private local AI prompt",err)
        self.assertEqual(worker.generation_calls,1)
        self.assertEqual(len(worker.spine.receipts),0)

    def test_native_error_never_triggers_implicit_second_forward_pass(self):
        def fail(*args,**kwargs):
            self.worker.generation_calls+=1
            raise RuntimeError("simulated native uncertainty")
        self.worker.turn=fail
        status,out,err,worker,activate=invoke(
            cli_args("--approve-real-acceptance"),
            worker=self.worker,
        )
        self.assertEqual(status,2)
        self.assertFalse(out)
        self.assertNotIn("simulated native uncertainty",err)
        self.assertEqual(worker.generation_calls,1)

    def test_invalid_utf8_prompt_denied_before_model_start(self):
        status,out,err,worker,activate=invoke(
            cli_args("--approve-real-acceptance"),
            input_data=b"\xff\xff\xff",
        )
        self.assertEqual(status,2)
        self.assertFalse(out)
        activate.assert_not_called()
        self.assertEqual(worker.generation_calls,0)

    def test_oversized_prompt_denied_without_loading_model(self):
        status,out,err,worker,activate=invoke(
            cli_args("--approve-real-acceptance"),
            input_data=b"x"*32769,
        )
        self.assertEqual(status,2)
        self.assertFalse(out)
        activate.assert_not_called()
        self.assertEqual(worker.generation_calls,0)

    def test_preexisting_replay_cannot_count_as_fresh_native_acceptance(self):
        from skeleton.ai.runtime.operational_ai.laptop_runtime import first_turn_acceptance
        from skeleton.ai.runtime.operational_ai.laptop_runtime.identity import ActiveModel
        fake_bridge=mock.Mock()
        fake_bridge.identity=ActiveModel.from_supervisor(self.worker)
        fake_bridge.turn.return_value={
            "replayed":True,
            "generated_tokens":1,
            "output_sha256":OUTPUT_SHA,
        }
        with mock.patch.object(
            first_turn_acceptance,"TurnBridge",return_value=fake_bridge
        ):
            with self.assertRaisesRegex(ContractViolation,"fresh native"):
                run_acceptance(self.worker,prompt="private",approved=True)
        self.assertEqual(self.worker.generation_calls,0)

    def test_zero_new_tokens_does_not_prove_first_turn(self):
        from skeleton.ai.runtime.operational_ai.laptop_runtime import first_turn_acceptance
        from skeleton.ai.runtime.operational_ai.laptop_runtime.identity import ActiveModel
        fake_bridge=mock.Mock()
        fake_bridge.identity=ActiveModel.from_supervisor(self.worker)
        fake_bridge.turn.return_value={
            "replayed":False,
            "generated_tokens":0,
            "output_sha256":OUTPUT_SHA,
        }
        with mock.patch.object(
            first_turn_acceptance,"TurnBridge",return_value=fake_bridge
        ):
            with self.assertRaisesRegex(ContractViolation,"output token"):
                run_acceptance(self.worker,prompt="private",approved=True)
        self.assertEqual(self.worker.generation_calls,0)

if __name__=="__main__":
    unittest.main()
