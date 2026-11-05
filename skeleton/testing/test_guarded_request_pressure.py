"""Live domain acceptance for pressure; no model-quality certification."""
from __future__ import annotations
import unittest
from skeleton.ai.runtime.operational_ai.guarded_request.scenario_runner import iter_scenarios
from skeleton.ai.runtime.operational_ai.guarded_request.policy_oracle import evaluate
from skeleton.ai.runtime.operational_ai.guarded_request.pressure import Pressure, PressurePolicy
from skeleton.ai.runtime.operational_ai.guarded_request.errors import GateDenied

class TestPressureGuard(unittest.TestCase):
    def test_all_24_independent_vectors(self):
        cases = [case for case in iter_scenarios() if case['control'] == 'pressure']
        self.assertEqual(len(cases), 24)
        self.assertEqual(len({case['id'] for case in cases}), 24)
        for case in cases:
            with self.subTest(vector=case['id']):
                result = evaluate(case['control'], case['input'])
                self.assertIs(result['allowed'], case['expected_allow'])
                self.assertTrue(result['code'])
    def test_both_allow_and_denial_are_present(self):
        cases = [case for case in iter_scenarios() if case['control'] == 'pressure']
        self.assertTrue(any(case['expected_allow'] for case in cases))
        self.assertTrue(any(not case['expected_allow'] for case in cases))

    def test_freshness_and_threshold(self):
        policy = PressurePolicy()
        self.assertEqual(policy.decide(Pressure(0.2, 0.1, 0.3, 5), 5), "healthy")
        self.assertEqual(policy.decide(Pressure(0.7, 0.1, 0.2, 5), 5), "degraded")
        with self.assertRaises(GateDenied):
            policy.decide(Pressure(0.9, 0.1, 0.2, 5), 5)
    def test_stale_telemetry_never_green(self):
        with self.assertRaises(GateDenied):
            PressurePolicy().decide(Pressure(0.0, 0.0, 0.0, 0), 2000)


if __name__ == '__main__':
    unittest.main()
