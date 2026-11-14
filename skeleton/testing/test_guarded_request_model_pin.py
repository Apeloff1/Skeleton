"""Live domain acceptance for model_pin; no model-quality certification."""
from __future__ import annotations
import unittest
from skeleton.ai.runtime.operational_ai.guarded_request.scenario_runner import iter_scenarios
from skeleton.ai.runtime.operational_ai.guarded_request.policy_oracle import evaluate
import hashlib
from skeleton.ai.runtime.operational_ai.guarded_request.model_pins import ModelPin
from skeleton.ai.runtime.operational_ai.guarded_request.errors import GateDenied

class TestModelPinGuard(unittest.TestCase):
    def test_all_24_independent_vectors(self):
        cases = [case for case in iter_scenarios() if case['control'] == 'model_pin']
        self.assertEqual(len(cases), 24)
        self.assertEqual(len({case['id'] for case in cases}), 24)
        for case in cases:
            with self.subTest(vector=case['id']):
                result = evaluate(case['control'], case['input'])
                self.assertIs(result['allowed'], case['expected_allow'])
                self.assertTrue(result['code'])
    def test_both_allow_and_denial_are_present(self):
        cases = [case for case in iter_scenarios() if case['control'] == 'model_pin']
        self.assertTrue(any(case['expected_allow'] for case in cases))
        self.assertTrue(any(not case['expected_allow'] for case in cases))

    def test_exact_checkpoint_bytes(self):
        blob = b"approved-local-test-checkpoint"
        sha = hashlib.sha256(blob).hexdigest()
        model = ModelPin("local_model", sha, "b"*64, len(blob), "operator-reviewed")
        model.verify(blob, reported_tokenizer_sha256="b"*64)
        with self.assertRaises(GateDenied):
            model.verify(blob+b"x", reported_tokenizer_sha256="b"*64)
        with self.assertRaises(GateDenied):
            model.verify(blob, reported_tokenizer_sha256="c"*64)
    def test_no_fake_empty_model(self):
        with self.assertRaises(GateDenied):
            ModelPin("native", "a"*64, "b"*64, 0, "approved")


if __name__ == '__main__':
    unittest.main()
