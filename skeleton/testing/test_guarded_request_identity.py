"""Live domain acceptance for identity; no model-quality certification."""
from __future__ import annotations
import unittest
from skeleton.ai.runtime.operational_ai.guarded_request.scenario_runner import iter_scenarios
from skeleton.ai.runtime.operational_ai.guarded_request.policy_oracle import evaluate
from skeleton.ai.runtime.operational_ai.guarded_request.identities import require_id
from skeleton.ai.runtime.operational_ai.guarded_request.errors import GateDenied

class TestIdentityGuard(unittest.TestCase):
    def test_all_24_independent_vectors(self):
        cases = [case for case in iter_scenarios() if case['control'] == 'identity']
        self.assertEqual(len(cases), 24)
        self.assertEqual(len({case['id'] for case in cases}), 24)
        for case in cases:
            with self.subTest(vector=case['id']):
                result = evaluate(case['control'], case['input'])
                self.assertIs(result['allowed'], case['expected_allow'])
                self.assertTrue(result['code'])
    def test_both_allow_and_denial_are_present(self):
        cases = [case for case in iter_scenarios() if case['control'] == 'identity']
        self.assertTrue(any(case['expected_allow'] for case in cases))
        self.assertTrue(any(not case['expected_allow'] for case in cases))

    def test_identity_edge(self):
        self.assertEqual(require_id("tenant_01"), "tenant_01")
        for bad in ("", "Tenant", "x/../z", "x"*65, "a\x00"):
            with self.subTest(value=repr(bad)), self.assertRaises(GateDenied):
                require_id(bad)
    def test_namespace_is_not_path(self):
        for literal in ("../private", "etc/passwd", "root:admin", "name.txt"):
            with self.assertRaises(GateDenied):
                require_id(literal)


if __name__ == '__main__':
    unittest.main()
