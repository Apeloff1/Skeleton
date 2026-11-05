"""Pinned corpus identity: no substituted 480-case success can certify."""
from __future__ import annotations
from dataclasses import replace
import unittest

from skeleton.ai.runtime.operational_ai.native_qualification.corpus import (
    DOMAINS, CASES_PER_DOMAIN, TOTAL_CASES, iter_cases,
    verify_exact_complete, inventory,
)


class TestOriginalCorpus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = tuple(iter_cases())

    def test_exact_source_inventory(self):
        self.assertEqual(len(DOMAINS),20)
        self.assertEqual(CASES_PER_DOMAIN,24)
        self.assertEqual(TOTAL_CASES,480)
        self.assertEqual(len(self.cases),480)

    def test_full_original_corpus_proof(self):
        self.assertTrue(verify_exact_complete(self.cases))

    def test_swapped_task_is_not_full(self):
        changed = list(self.cases)
        changed[-1] = replace(changed[-1], objective="changed quality task")
        self.assertFalse(verify_exact_complete(tuple(changed)))

    def test_deleted_task_is_not_full(self):
        self.assertFalse(verify_exact_complete(self.cases[:-1]))

    def test_duplicate_task_is_not_full(self):
        changed = list(self.cases)
        changed[-1] = changed[0]
        self.assertFalse(verify_exact_complete(tuple(changed)))

    def test_distinct_original_licenses(self):
        self.assertTrue(all(case.license_id == "original_fixture" for case in self.cases))

    def test_inventory_never_claims_model_run(self):
        report = inventory()
        self.assertEqual(report["count"],480)
        self.assertFalse(report["actual_model_tested"])
        self.assertFalse(report["qualification_issued"])
        self.assertEqual(len(report["case_content"]),480)


if __name__ == "__main__":
    unittest.main()
