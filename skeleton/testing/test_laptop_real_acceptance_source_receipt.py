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
    input_stream=SimpleNamespace(buffer=BytesIO(input_data))
    output=StringIO()
    error=StringIO()
    with (
        mock.patch(
            "skeleton.ai.runtime.operational_ai.laptop_runtime.cli.activate_checked",
            return_value=(nullcontext(),fake,object()),
        ) as activate,
        mock.patch(
            "skeleton.ai.runtime.operational_ai.laptop_runtime.cli.sys.stdin",
            input_stream,
        ),
        redirect_stdout(output),
        redirect_stderr(error),
    ):
        status=cli_main(args)
    return status,output.getvalue(),error.getvalue(),fake,activate


class FirstTurnReceiptEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.worker=FakeWorker()

    def test_direct_function_requires_explicit_operator_approval(self):
        with self.assertRaisesRegex(ContractViolation,"approval required"):
            run_acceptance(self.worker,prompt="hello")
        self.assertEqual(self.worker.generation_calls,0)
        self.assertEqual(len(self.worker.spine.created),0)

    def test_explicitly_admitted_test_captures_exact_model_and_replay_identity(self):
        record=run_acceptance(
            self.worker,prompt="private local fake model task",approved=True,
        )
        self.assertEqual(record["schema"],"laptop-real-first-turn-e2e.v1")
        self.assertEqual(record["model_sha256"],MODEL)
        self.assertEqual(record["tokenizer_sha256"],TOKENIZER)
        self.assertEqual(record["output_sha256"],OUTPUT_SHA)
        self.assertEqual(len(record["session_id"]),34)
        self.assertEqual(len(record["request_id"]),34)
        self.assertEqual(self.worker.generation_calls,1)
        self.assertEqual(len(self.worker.spine.receipts),1)
        self.assertFalse(record["native_model_observed"])
        self.assertFalse(record["installed_source_bound"])
        self.assertEqual(
            record["evidence_grade"], "source-only-simulated-or-unverified"
        )
        self.assertIsNone(record["installed_source"])
        self.assertFalse(record["operator_approved_real_inference"])
        self.assertFalse(record["release_certified"])
        self.assertFalse(record["device_qualified"])

    def test_read_only_replay_probe_does_not_generate_twice(self):
        from skeleton.ai.runtime.operational_ai.laptop_runtime import (
            first_turn_acceptance,
        )
        original=first_turn_acceptance.inspect_replay
        seen=[]
        def observe(*args,**kwargs):
            seen.append((args[1],args[2]))
            return original(*args,**kwargs)
        with mock.patch.object(
            first_turn_acceptance,"inspect_replay",side_effect=observe
        ):
            record=run_acceptance(
                self.worker,prompt="privately reason",approved=True,
            )
        self.assertEqual(len(seen),1)
        self.assertEqual(seen[0][0],record["session_id"])
        self.assertEqual(seen[0][1],record["request_id"])
        self.assertEqual(self.worker.generation_calls,1)

    def test_model_epoch_change_after_replay_denies_evidence_publication(self):
        from skeleton.ai.runtime.operational_ai.laptop_runtime import (
            first_turn_acceptance,
        )
        original=first_turn_acceptance.inspect_replay
        def changed_after_read(*args,**kwargs):
            receipt=original(*args,**kwargs)
            self.worker.spine.backend.model_digest="c"*64
            return receipt
        with mock.patch.object(
            first_turn_acceptance,
            "inspect_replay",
            side_effect=changed_after_read,
        ):
            with self.assertRaises(ContractViolation):
                run_acceptance(
                    self.worker,prompt="private task",approved=True,
                )
        self.assertEqual(self.worker.generation_calls,1)
        self.assertEqual(len(self.worker.spine.receipts),1)

    def test_tokenizer_epoch_change_after_replay_denies_evidence(self):
        from skeleton.ai.runtime.operational_ai.laptop_runtime import (
            first_turn_acceptance,
        )
        original=first_turn_acceptance.inspect_replay
        def changed_after_read(*args,**kwargs):
            receipt=original(*args,**kwargs)
            self.worker.spine.backend.tokenizer_digest="d"*64
            return receipt
        with mock.patch.object(
            first_turn_acceptance,
            "inspect_replay",
            side_effect=changed_after_read,
        ):
            with self.assertRaises(ContractViolation):
                run_acceptance(
                    self.worker,prompt="private task",approved=True,
                )
        self.assertEqual(self.worker.generation_calls,1)

if __name__=="__main__":
    unittest.main()
