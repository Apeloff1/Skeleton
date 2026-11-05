"""Live domain acceptance for stream; no model-quality certification."""
from __future__ import annotations
import unittest
from skeleton.ai.runtime.operational_ai.guarded_request.scenario_runner import iter_scenarios
from skeleton.ai.runtime.operational_ai.guarded_request.policy_oracle import evaluate
from skeleton.ai.runtime.operational_ai.guarded_request.stream import StreamFence
from skeleton.ai.runtime.operational_ai.guarded_request.errors import GateDenied

class TestStreamGuard(unittest.TestCase):
    def test_all_24_independent_vectors(self):
        cases = [case for case in iter_scenarios() if case['control'] == 'stream']
        self.assertEqual(len(cases), 24)
        self.assertEqual(len({case['id'] for case in cases}), 24)
        for case in cases:
            with self.subTest(vector=case['id']):
                result = evaluate(case['control'], case['input'])
                self.assertIs(result['allowed'], case['expected_allow'])
                self.assertTrue(result['code'])
    def test_both_allow_and_denial_are_present(self):
        cases = [case for case in iter_scenarios() if case['control'] == 'stream']
        self.assertTrue(any(case['expected_allow'] for case in cases))
        self.assertTrue(any(not case['expected_allow'] for case in cases))

    def test_multibyte_split(self):
        fence = StreamFence(max_bytes=10)
        self.assertEqual(fence.push(b"\xc3"), "")
        self.assertEqual(fence.push(b"\xa9"), "é")
        self.assertEqual(fence.finish(), "é")
    def test_no_partial_overbudget_accept(self):
        fence = StreamFence(max_bytes=2)
        fence.push(b"a")
        with self.assertRaises(GateDenied):
            fence.push(b"zz")
        self.assertEqual(fence.consumed_bytes, 1)
        self.assertEqual(fence.finish(), "a")


if __name__ == '__main__':
    unittest.main()
