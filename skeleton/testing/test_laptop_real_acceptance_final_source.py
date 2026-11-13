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


class FinalInstalledSourceWitnessTests(unittest.TestCase):
    def setUp(self):
        self.worker=FakeWorker()

    def test_two_source_checks_enclose_exactly_one_model_generation(self):
        with mock.patch.object(
            first_turn_acceptance,"require_activated_source",
            side_effect=[dict(SOURCE),dict(SOURCE)],
        ) as source:
            record=test_turn(self.worker)
        self.assertEqual(source.call_count,2)
        self.assertEqual(record["model_sha256"],MODEL)
        self.assertEqual(record["tokenizer_sha256"],TOKENIZER)
        self.assertTrue(record["replayed_without_generation"])
        self.assertTrue(record["installed_source_bound"])
        self.assertEqual(self.worker.generation_calls,1)
        self.assertEqual(len(self.worker.spine.receipts),1)
        self.assertFalse(record["device_qualified"])
        self.assertFalse(record["release_certified"])

    def test_final_source_manifest_change_denies_after_single_sqlite_commit(self):
        with mock.patch.object(
            first_turn_acceptance,"require_activated_source",
            side_effect=[
                dict(SOURCE),
                {**SOURCE,"manifest_sha256":"f"*64},
            ],
        ) as source:
            with self.assertRaisesRegex(
                ContractViolation,"source changed after model generation"
            ):
                test_turn(self.worker)
        self.assertEqual(source.call_count,2)
        self.assertEqual(self.worker.generation_calls,1)
        self.assertEqual(len(self.worker.spine.receipts),1)

    def test_final_source_archive_revision_change_denies(self):
        for key,value in (
            ("archive_sha256","f"*64),
            ("source_sha","f"*40),
            ("installed_model_bytes",8192),
        ):
            worker=FakeWorker()
            with self.subTest(key=key),mock.patch.object(
                first_turn_acceptance,"require_activated_source",
                side_effect=[dict(SOURCE),{**SOURCE,key:value}],
            ):
                with self.assertRaises(ContractViolation):
                    test_turn(worker)
            self.assertEqual(worker.generation_calls,1)
            self.assertEqual(len(worker.spine.receipts),1)

    def test_final_source_lease_error_holds_without_second_native_attempt(self):
        with mock.patch.object(
            first_turn_acceptance,"require_activated_source",
            side_effect=[
                dict(SOURCE),
                ContractViolation("native capacity lease expired"),
            ],
        ):
            with self.assertRaisesRegex(ContractViolation,"lease expired"):
                test_turn(self.worker)
        self.assertEqual(self.worker.generation_calls,1)
        self.assertEqual(len(self.worker.spine.receipts),1)

    def test_tokenizer_change_after_final_source_witness_holds_output(self):
        counter={"count":0}
        def attestation(*args):
            counter["count"]+=1
            if counter["count"]==2:
                self.worker.spine.backend.tokenizer_digest="c"*64
            return dict(SOURCE)
        with mock.patch.object(
            first_turn_acceptance,"require_activated_source",
            side_effect=attestation,
        ):
            # The canonical identity checker can reject the changed
            # tokenizer earlier as an active-backend/principal mismatch.
            with self.assertRaises(ContractViolation):
                test_turn(self.worker)
        self.assertEqual(counter["count"],2)
        self.assertEqual(self.worker.generation_calls,1)

    def test_subject_change_after_final_source_witness_holds_output(self):
        def observe(*args):
            observe.count+=1
            if observe.count==2:
                self.worker.spine.identity.subject="foreign"
            return dict(SOURCE)
        observe.count=0
        with mock.patch.object(
            first_turn_acceptance,"require_activated_source",
            side_effect=observe,
        ):
            with self.assertRaisesRegex(ContractViolation,"principal changed"):
                test_turn(self.worker)
        self.assertEqual(observe.count,2)
        self.assertEqual(self.worker.generation_calls,1)

    def test_uncommitted_worker_effect_does_not_trigger_second_source_witness(self):
        original=self.worker.turn
        def omit_durable_commit(*args, **kwargs):
            reply=original(*args, **kwargs)
            # FakeWorker is not SimulatedWorker: deliberately remove its
            # SQLite-shaped receipt to exercise actual fail-closed replay.
            self.worker.spine.receipts.clear()
            return reply
        with (
            mock.patch.object(self.worker,"turn",side_effect=omit_durable_commit),
            mock.patch.object(
                first_turn_acceptance,"require_activated_source",
                return_value=dict(SOURCE),
            ) as source,
        ):
            with self.assertRaises(ContractViolation):
                test_turn(self.worker)
        self.assertEqual(source.call_count,1)
        self.assertEqual(self.worker.generation_calls,1)
        self.assertFalse(self.worker.spine.receipts)


if __name__=="__main__":
    unittest.main()
