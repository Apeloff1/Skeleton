"""Live domain acceptance for transport; no model-quality certification."""
from __future__ import annotations
import unittest
from skeleton.ai.runtime.operational_ai.guarded_request.scenario_runner import iter_scenarios
from skeleton.ai.runtime.operational_ai.guarded_request.policy_oracle import evaluate
from skeleton.ai.runtime.operational_ai.guarded_request.transport_gate import LoopbackGate
from skeleton.ai.runtime.operational_ai.guarded_request.errors import GateDenied

class TestTransportGuard(unittest.TestCase):
    def test_all_24_independent_vectors(self):
        cases = [case for case in iter_scenarios() if case['control'] == 'transport']
        self.assertEqual(len(cases), 24)
        self.assertEqual(len({case['id'] for case in cases}), 24)
        for case in cases:
            with self.subTest(vector=case['id']):
                result = evaluate(case['control'], case['input'])
                self.assertIs(result['allowed'], case['expected_allow'])
                self.assertTrue(result['code'])
    def test_both_allow_and_denial_are_present(self):
        cases = [case for case in iter_scenarios() if case['control'] == 'transport']
        self.assertTrue(any(case['expected_allow'] for case in cases))
        self.assertTrue(any(not case['expected_allow'] for case in cases))

    def test_bound_bearer(self):
        gate = LoopbackGate("X"*48)
        headers = {"content-type": "application/json", "authorization": "Bearer "+"X"*48}
        gate.authorize(peer_ip="127.0.0.1", host="127.0.0.1",
                       method="POST", route="/v1/operations", headers=headers,
                       body_length=128)
        with self.assertRaises(GateDenied):
            gate.authorize(peer_ip="8.8.8.8", host="127.0.0.1",
                           method="POST", route="/v1/operations",
                           headers=headers, body_length=128)
    def test_browser_origin_denied(self):
        gate = LoopbackGate("X"*48)
        with self.assertRaises(GateDenied):
            gate.authorize(peer_ip="127.0.0.1", host="127.0.0.1",
                           method="POST", route="/v1/operations",
                           headers={"content-type":"application/json",
                                    "authorization":"Bearer "+"X"*48,
                                    "origin":"null"}, body_length=1)


if __name__ == '__main__':
    unittest.main()
