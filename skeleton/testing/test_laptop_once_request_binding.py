"""Test-double immutable native request binding matches canonical SQLite CAS.

The test source is not a real model, device or independent source receipt.
Every collision is a denial before the simulated native generation counter.
"""
from __future__ import annotations

import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
from skeleton.ai.runtime.operational_ai.laptop_runtime.run_once import generate_once
from skeleton.testing.laptop_runtime_test_support import FakeWorker, MODEL


class TestFakeRequestIdentity(unittest.TestCase):
    def setUp(self):
        self.worker = FakeWorker()
        self.worker.spine.create("s_test")

    def test_duplicate_id_with_changed_prompt_denied_before_generation(self):
        self.worker.turn("s_test", "r1", "alpha")
        with self.assertRaisesRegex(ContractViolation, "different input"):
            self.worker.turn("s_test", "r1", "beta")
        self.assertEqual(self.worker.generation_calls, 1)
        self.assertEqual(len(self.worker.spine.receipts), 1)

    def test_duplicate_id_with_changed_seed_denied(self):
        self.worker.turn("s_test", "r1", "alpha", seed=3)
        with self.assertRaises(ContractViolation):
            self.worker.turn("s_test", "r1", "alpha", seed=4)
        self.assertEqual(self.worker.generation_calls, 1)

    def test_duplicate_id_with_changed_temperature_denied(self):
        self.worker.turn("s_test", "r1", "alpha", temperature=0.6)
        with self.assertRaises(ContractViolation):
            self.worker.turn("s_test", "r1", "alpha", temperature=0.9)
        self.assertEqual(self.worker.generation_calls, 1)

    def test_exact_duplicate_returns_committed_replay(self):
        initial = self.worker.turn(
            "s_test", "r1", "alpha", seed=5, temperature=0.7,
        )
        second = self.worker.turn(
            "s_test", "r1", "alpha", seed=5, temperature=0.7,
        )
        self.assertFalse(initial["replayed"])
        self.assertTrue(second["replayed"])
        self.assertEqual(initial["output_sha256"], second["output_sha256"])
        self.assertEqual(self.worker.generation_calls, 1)

    def test_distinct_request_ids_remain_independent(self):
        self.worker.turn("s_test", "r1", "alpha")
        self.worker.turn("s_test", "r2", "beta")
        self.assertEqual(self.worker.generation_calls, 2)
        self.assertEqual(len(self.worker.spine.receipts), 2)

    def test_same_request_id_in_distinct_owned_sessions_is_independent(self):
        self.worker.spine.create("s_other")
        self.worker.turn("s_test", "r1", "alpha")
        self.worker.turn("s_other", "r1", "beta")
        self.assertEqual(self.worker.generation_calls, 2)

    def test_collision_does_not_destroy_original_replay(self):
        self.worker.turn("s_test", "r1", "alpha")
        with self.assertRaises(ContractViolation):
            self.worker.turn("s_test", "r1", "other")
        committed = self.worker.spine.replay(
            "s_test", "r1", "alpha", seed=0, temperature=0.8,
        )
        self.assertTrue(committed["replayed"])
        self.assertEqual(self.worker.generation_calls, 1)

    def test_changed_prompt_replay_probe_is_not_a_false_success(self):
        self.worker.turn("s_test", "r1", "alpha")
        replay = self.worker.spine.replay(
            "s_test", "r1", "other", seed=0, temperature=0.8,
        )
        self.assertIsNone(replay)
        self.assertEqual(self.worker.generation_calls, 1)

    def test_canonical_generate_once_rejects_replayed_id_with_new_prompt(self):
        first = generate_once(
            self.worker, "alpha", session="s_test", request_id="same",
        )
        self.assertEqual(first["receipt"]["model_sha256"], MODEL)
        with self.assertRaises(ContractViolation):
            generate_once(
                self.worker, "beta", session="s_test", request_id="same",
            )
        self.assertEqual(self.worker.generation_calls, 1)
        replay = generate_once(
            self.worker, "alpha", session="s_test", request_id="same",
        )
        self.assertTrue(replay["receipt"]["replayed"])
        self.assertEqual(self.worker.generation_calls, 1)


if __name__ == "__main__":
    unittest.main()
