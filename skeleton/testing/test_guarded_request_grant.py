"""Live domain acceptance for grant; no model-quality certification."""
from __future__ import annotations
import unittest
from skeleton.ai.runtime.operational_ai.guarded_request.scenario_runner import iter_scenarios
from skeleton.ai.runtime.operational_ai.guarded_request.policy_oracle import evaluate
from skeleton.ai.runtime.operational_ai.guarded_request.grants import ReadGrant
from skeleton.ai.runtime.operational_ai.guarded_request.identities import Scope
from skeleton.ai.runtime.operational_ai.guarded_request.errors import GateDenied

class TestGrantGuard(unittest.TestCase):
    def test_all_24_independent_vectors(self):
        cases = [case for case in iter_scenarios() if case['control'] == 'grant']
        self.assertEqual(len(cases), 24)
        self.assertEqual(len({case['id'] for case in cases}), 24)
        for case in cases:
            with self.subTest(vector=case['id']):
                result = evaluate(case['control'], case['input'])
                self.assertIs(result['allowed'], case['expected_allow'])
                self.assertTrue(result['code'])
    def test_both_allow_and_denial_are_present(self):
        cases = [case for case in iter_scenarios() if case['control'] == 'grant']
        self.assertTrue(any(case['expected_allow'] for case in cases))
        self.assertTrue(any(not case['expected_allow'] for case in cases))

    def test_cross_tenant_denied(self):
        scope = Scope("tenant", "alice", "s1", "a"*64)
        grant = ReadGrant(scope, frozenset({"hash_text"}), 1000)
        grant.check(scope=scope, tool="hash_text", now_ns=20)
        with self.assertRaises(GateDenied):
            grant.check(scope=Scope("other", "alice", "s1", "a"*64),
                        tool="hash_text", now_ns=20)
    def test_effect_never_model_granted(self):
        scope = Scope("tenant", "alice", "s1", "a"*64)
        with self.assertRaises(GateDenied):
            ReadGrant(scope, frozenset({"shell"}), 1000)
        with self.assertRaises(GateDenied):
            ReadGrant(scope, frozenset({"hash_text"}), 1000).check(
                scope=scope, tool="hash_text", now_ns=1, mutating=True)


if __name__ == '__main__':
    unittest.main()
