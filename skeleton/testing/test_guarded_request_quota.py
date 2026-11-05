"""Live domain acceptance for quota; no model-quality certification."""
from __future__ import annotations
import unittest
from skeleton.ai.runtime.operational_ai.guarded_request.scenario_runner import iter_scenarios
from skeleton.ai.runtime.operational_ai.guarded_request.policy_oracle import evaluate
from skeleton.ai.runtime.operational_ai.guarded_request.budgets import Quota, QuotaUsage
from skeleton.ai.runtime.operational_ai.guarded_request.errors import GateDenied

class TestQuotaGuard(unittest.TestCase):
    def test_all_24_independent_vectors(self):
        cases = [case for case in iter_scenarios() if case['control'] == 'quota']
        self.assertEqual(len(cases), 24)
        self.assertEqual(len({case['id'] for case in cases}), 24)
        for case in cases:
            with self.subTest(vector=case['id']):
                result = evaluate(case['control'], case['input'])
                self.assertIs(result['allowed'], case['expected_allow'])
                self.assertTrue(result['code'])
    def test_both_allow_and_denial_are_present(self):
        cases = [case for case in iter_scenarios() if case['control'] == 'quota']
        self.assertTrue(any(case['expected_allow'] for case in cases))
        self.assertTrue(any(not case['expected_allow'] for case in cases))

    def test_atomic_resource_charge(self):
        usage = QuotaUsage(Quota(input_bytes=5, output_bytes=4, tool_calls=1))
        usage.charge(input_bytes=3, output_bytes=2)
        before = usage.snapshot
        with self.assertRaises(GateDenied):
            usage.charge(input_bytes=3, output_bytes=2)
        self.assertEqual(usage.snapshot, before)
    def test_non_escalating_attenuation(self):
        quota = Quota()
        limited = quota.attenuate(output_tokens=64, tool_calls=0)
        self.assertEqual(limited.output_tokens, 64)
        with self.assertRaises(GateDenied):
            limited.attenuate(output_tokens=512)


if __name__ == '__main__':
    unittest.main()
