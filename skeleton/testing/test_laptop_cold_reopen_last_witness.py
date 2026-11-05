"""First-laptop cold-reopen source, identity and replay boundary tests.

Only the fake native worker is used; these cannot prove real GGUF inference,
hardware fitness, third-party model rights or release. All successful
production evidence requires the installed isolated model and SQLite spine.
"""
from __future__ import annotations

from unittest import mock
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime import (
    cold_reopen_acceptance,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
from skeleton.testing.laptop_runtime_test_support import FakeWorker, MODEL, TOKENIZER
from skeleton.testing.test_laptop_cold_reopen_source_custody import (
    SyntheticColdRig, SOURCE, OPTS,
)


class FinalNativeWitnessTests(unittest.TestCase):
    def test_source_is_inspected_before_and_after_reopened_replay(self):
        rig = SyntheticColdRig()
        with rig.patch() as (_, initial, source):
            record = cold_reopen_acceptance.run(**OPTS)
        self.assertEqual(initial.call_count, 2)
        self.assertEqual(source.call_count, 2)
        self.assertEqual(rig.second.generation_calls, 0)
        self.assertTrue(record["source_verified_twice"])
        self.assertFalse(record["physical_device_qualified"])

    def test_source_revision_swap_during_replay_denies_success(self):
        rig = SyntheticColdRig()
        with rig.patch() as (_, _, source):
            source.side_effect = [
                dict(SOURCE),
                {**SOURCE, "source_sha": "f" * 40},
            ]
            with self.assertRaisesRegex(
                ContractViolation, "source or resource lease changed"
            ):
                cold_reopen_acceptance.run(**OPTS)
        self.assertEqual(source.call_count, 2)
        self.assertEqual(rig.first.generation_calls, 1)
        self.assertEqual(rig.second.generation_calls, 0)
        self.assertIn("closed_2", rig.order)

    def test_backend_lease_revocation_after_sqlite_snapshot_denies_report(self):
        rig = SyntheticColdRig()
        with rig.patch() as (_, _, source):
            source.side_effect = [
                dict(SOURCE),
                ContractViolation("native capacity lease expired"),
            ]
            with self.assertRaisesRegex(ContractViolation, "lease expired"):
                cold_reopen_acceptance.run(**OPTS)
        self.assertEqual(source.call_count, 2)
        self.assertEqual(rig.second.generation_calls, 0)
        self.assertIn("closed_2", rig.order)

    def test_model_epoch_swap_during_read_denies_replay(self):
        rig = SyntheticColdRig()
        def mutate_when_reading():
            original = rig.first.spine.replay
            def swap(*args, **kwargs):
                result = original(*args, **kwargs)
                rig.first.spine.backend.model_digest = "f" * 64
                return result
            rig.first.spine.replay = swap
        rig.after_first = mutate_when_reading
        with rig.patch():
            with self.assertRaises(ContractViolation):
                cold_reopen_acceptance.run(**OPTS)
        self.assertEqual(rig.first.generation_calls, 1)
        self.assertEqual(rig.second.generation_calls, 0)
        self.assertIn("closed_2", rig.order)

    def test_rights_source_witness_must_remain_a_mapping(self):
        for invalid in (None, True, "approved", ["fake"], ()):
            rig = SyntheticColdRig()
            with self.subTest(invalid=repr(invalid)), rig.patch() as (_, _, source):
                source.side_effect = [dict(SOURCE), invalid]
                with self.assertRaises(ContractViolation):
                    cold_reopen_acceptance.run(**OPTS)
            self.assertEqual(rig.first.generation_calls, 1)
            self.assertEqual(rig.second.generation_calls, 0)
            self.assertIn("closed_2", rig.order)

    def test_unknown_model_health_after_replay_is_never_release(self):
        rig = SyntheticColdRig()
        with rig.patch():
            record = cold_reopen_acceptance.run(**OPTS)
        self.assertFalse(record["physical_device_qualified"])
        self.assertFalse(record["release_certified"])
        self.assertFalse(record["private_prompt_disclosed"])
        self.assertFalse(record["second_generation_attempted"])


if __name__ == "__main__":
    unittest.main()
