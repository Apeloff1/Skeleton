"""Real installed-source first-turn custody with a synthetic worker fixture.

This tests hold semantics only. All positive source witnesses here are patched
test doubles, not physical GGUF execution, independent model rights, device
pressure qualification, Windows/WSL2 evidence or release certification.
"""
from __future__ import annotations

from unittest import mock
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime import first_turn_acceptance
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
from skeleton.testing.laptop_runtime_test_support import FakeWorker, MODEL, TOKENIZER
from skeleton.testing.test_laptop_cold_reopen_source_custody import SOURCE


def test_turn(worker, **overrides):
    args={
        "prompt":"  local model task\n",
        "approved":True,
        "installed_receipt":object(),
        "require_real":True,
    }
    args.update(overrides)
    return first_turn_acceptance.run(worker, **args)


class FirstTurnSourceShapeTests(unittest.TestCase):
    def setUp(self):
        self.worker=FakeWorker()

    def test_malformed_first_source_proof_refused_before_sqlite_create(self):
        invalid=[
            None,True,False,0,"verified",[],{},{"model_sha256":MODEL},
            {**SOURCE,"unexpected_native_capability":True},
        ]
        for proof in invalid:
            with self.subTest(type=type(proof).__name__),mock.patch.object(
                first_turn_acceptance,"require_activated_source",
                return_value=proof,
            ) as source:
                with self.assertRaises(ContractViolation):
                    test_turn(self.worker)
                self.assertEqual(source.call_count,1)
                self.assertEqual(self.worker.generation_calls,0)
                self.assertFalse(self.worker.spine.created)

    def test_malformed_second_source_proof_does_not_erase_sqlite_receipt(self):
        for proof in (None,True,False,{},["approved"]):
            worker=FakeWorker()
            with self.subTest(type=type(proof).__name__),mock.patch.object(
                first_turn_acceptance,"require_activated_source",
                side_effect=[dict(SOURCE),proof],
            ):
                with self.assertRaises(ContractViolation):
                    test_turn(worker)
            self.assertEqual(worker.generation_calls,1)
            self.assertEqual(len(worker.spine.receipts),1)

    def test_installed_source_absent_cannot_be_promoted_to_real(self):
        with self.assertRaisesRegex(ContractViolation,"source proof required"):
            first_turn_acceptance.run(
                self.worker,prompt="private",approved=True,require_real=True,
                installed_receipt=None,
            )
        self.assertEqual(self.worker.generation_calls,0)
        self.assertFalse(self.worker.spine.created)

    def test_synthetic_source_only_never_observes_real_model(self):
        record=first_turn_acceptance.run(
            self.worker,prompt="private",approved=True,
            installed_receipt=None,require_real=False,
        )
        self.assertIs(record["installed_source_bound"],False)
        self.assertIs(record["native_model_observed"],False)
        self.assertIs(record["operator_approved_real_inference"],False)
        self.assertEqual(record["evidence_grade"],
                         "source-only-simulated-or-unverified")
        self.assertIs(record["release_certified"],False)
        self.assertEqual(self.worker.generation_calls,1)

    def test_exact_source_witness_never_contains_private_task(self):
        private_prompt="  strict private local task\n"
        with mock.patch.object(
            first_turn_acceptance,"require_activated_source",
            return_value=dict(SOURCE),
        ) as witness:
            receipt=test_turn(self.worker,prompt=private_prompt)
        self.assertEqual(witness.call_count,2)
        self.assertNotIn("prompt",receipt)
        self.assertNotIn("text",receipt)
        self.assertNotIn(private_prompt,str(receipt))
        self.assertNotIn("private local",str(receipt))
        self.assertEqual(self.worker.generation_calls,1)

    def test_invalid_user_prompt_is_never_a_native_forward_pass(self):
        for prompt in (None,0,True,[],{}," ","\ud800","bad\x00prompt"):
            with self.subTest(value=repr(prompt)),mock.patch.object(
                first_turn_acceptance,"require_activated_source",
                return_value=dict(SOURCE),
            ):
                with self.assertRaises(ContractViolation):
                    test_turn(self.worker,prompt=prompt)
                self.assertEqual(self.worker.generation_calls,0)
                self.assertFalse(self.worker.spine.created)


if __name__=="__main__":
    unittest.main()
