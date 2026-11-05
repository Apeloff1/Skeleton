"""Live domain acceptance for nonce; no model-quality certification."""
from __future__ import annotations
import unittest
from skeleton.ai.runtime.operational_ai.guarded_request.scenario_runner import iter_scenarios
from skeleton.ai.runtime.operational_ai.guarded_request.policy_oracle import evaluate
import sqlite3
from skeleton.ai.runtime.operational_ai.guarded_request.nonce_fence import NonceFence
from skeleton.ai.runtime.operational_ai.guarded_request.errors import GateDenied

class TestNonceGuard(unittest.TestCase):
    def test_all_24_independent_vectors(self):
        cases = [case for case in iter_scenarios() if case['control'] == 'nonce']
        self.assertEqual(len(cases), 24)
        self.assertEqual(len({case['id'] for case in cases}), 24)
        for case in cases:
            with self.subTest(vector=case['id']):
                result = evaluate(case['control'], case['input'])
                self.assertIs(result['allowed'], case['expected_allow'])
                self.assertTrue(result['code'])
    def test_both_allow_and_denial_are_present(self):
        cases = [case for case in iter_scenarios() if case['control'] == 'nonce']
        self.assertTrue(any(case['expected_allow'] for case in cases))
        self.assertTrue(any(not case['expected_allow'] for case in cases))

    def test_monotonic_and_true_replay(self):
        with sqlite3.connect(":memory:", isolation_level=None) as db:
            fence = NonceFence(db)
            self.assertEqual(fence.reserve("tenant", "n1", 1, "a"*64), "admitted")
            self.assertEqual(fence.reserve("tenant", "n1", 1, "a"*64), "replayed")
            with self.assertRaises(GateDenied):
                fence.reserve("tenant", "n1", 1, "b"*64)
            with self.assertRaises(GateDenied):
                fence.reserve("tenant", "n2", 1, "a"*64)
            self.assertEqual(fence.head("tenant"), 1)
    def test_sequence_requires_real_integer(self):
        with sqlite3.connect(":memory:", isolation_level=None) as db:
            with self.assertRaises(GateDenied):
                NonceFence(db).reserve("tenant", "n1", True, "a"*64)


if __name__ == '__main__':
    unittest.main()
