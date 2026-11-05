"""A complete vector corpus never claims trained or released model quality."""
from __future__ import annotations
import unittest
from skeleton.ai.runtime.operational_ai.native_candidate.vector_catalog import (
    DOMAINS, PER_DOMAIN, read_cases, run_all,
)


class TestCandidateAdmissionMatrix(unittest.TestCase):
    def test_exact_source_inventory(self):
        cases=tuple(read_cases())
        self.assertEqual(len(DOMAINS),12)
        self.assertEqual(PER_DOMAIN,24)
        self.assertEqual(len(cases),288)
        self.assertEqual(len({c["id"] for c in cases}),288)

    def test_each_domain_has_allow_and_rejection(self):
        cases=tuple(read_cases())
        for domain in DOMAINS:
            group=[c for c in cases if c["domain"]==domain]
            self.assertEqual(len(group),24)
            self.assertTrue(any(c["expected_allow"] for c in group))
            self.assertTrue(any(not c["expected_allow"] for c in group))

    def test_real_policy_execution_matches_expected_cases(self):
        proof=run_all()
        self.assertEqual(proof["total"],288)
        self.assertEqual(proof["failed"],0,proof["failure_ids"])
        self.assertEqual(proof["passed"],288)
        self.assertFalse(proof["real_model_trained"])
        self.assertFalse(proof["model_qualified"])


if __name__ == "__main__":
    unittest.main()
