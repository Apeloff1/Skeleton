"""Live domain acceptance for evidence; no model-quality certification."""
from __future__ import annotations
import unittest
from skeleton.ai.runtime.operational_ai.guarded_request.scenario_runner import iter_scenarios
from skeleton.ai.runtime.operational_ai.guarded_request.policy_oracle import evaluate
import hashlib
from skeleton.ai.runtime.operational_ai.guarded_request.evidence import Citation
from skeleton.ai.runtime.operational_ai.guarded_request.errors import GateDenied

class TestEvidenceGuard(unittest.TestCase):
    def test_all_24_independent_vectors(self):
        cases = [case for case in iter_scenarios() if case['control'] == 'evidence']
        self.assertEqual(len(cases), 24)
        self.assertEqual(len({case['id'] for case in cases}), 24)
        for case in cases:
            with self.subTest(vector=case['id']):
                result = evaluate(case['control'], case['input'])
                self.assertIs(result['allowed'], case['expected_allow'])
                self.assertTrue(result['code'])
    def test_both_allow_and_denial_are_present(self):
        cases = [case for case in iter_scenarios() if case['control'] == 'evidence']
        self.assertTrue(any(case['expected_allow'] for case in cases))
        self.assertTrue(any(not case['expected_allow'] for case in cases))

    def test_unicode_byte_offsets(self):
        source = "aé💠z".encode("utf-8")
        item = Citation("source_1", hashlib.sha256(source).hexdigest(), 1, 3, "é")
        item.verify(source)
        with self.assertRaises(GateDenied):
            Citation("source_1", item.source_sha256, 1, 2, "é").verify(source)
    def test_no_citation_splice(self):
        source = b"trusted exact source"
        h = hashlib.sha256(source).hexdigest()
        with self.assertRaises(GateDenied):
            Citation("source_1", h, 0, 7, "guessed").verify(source)


if __name__ == '__main__':
    unittest.main()
