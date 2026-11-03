"""All 768 challenge records must match original independent task oracle."""
from __future__ import annotations
from dataclasses import replace
import unittest
from skeleton.ai.runtime.operational_ai.native_supervised.challenge_catalog import (
    iter_challenges,verify_exact,inventory,TOTAL,CASES_PER_DOMAIN,
)
from skeleton.ai.runtime.operational_ai.native_supervised.challenge_schema import (
    Challenge,SCHEMA,
)
from skeleton.ai.runtime.operational_ai.native_supervised.challenge_oracle import (
    synthesize,DOMAINS,CRITICAL,
)
from skeleton.ai.runtime.operational_ai.native_supervised.canonical import encode
from skeleton.ai.runtime.operational_ai.native_supervised.errors import SupervisedRejected


class TestChallengeIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases=tuple(iter_challenges())

    def test_full_32_domain_inventory(self):
        self.assertEqual(len(self.cases),TOTAL)
        self.assertEqual(TOTAL,768)
        self.assertEqual(CASES_PER_DOMAIN,24)
        self.assertEqual(len(DOMAINS),32)

    def test_exact_rights_and_content_proof(self):
        self.assertTrue(verify_exact(self.cases))
        inv=inventory()
        self.assertEqual(len(inv["entries"]),768)
        self.assertEqual(inv["count"],768)
        self.assertFalse(inv["trained_on_challenges"])

    def test_no_source_id_collisions(self):
        self.assertEqual(len({x.case_id for x in self.cases}),768)
        self.assertEqual(len({x.sha256 for x in self.cases}),768)

    def test_independent_answers_all_domains(self):
        for case in self.cases:
            with self.subTest(id=case.case_id):
                args,prompt,answer=synthesize(case.domain,case.ordinal)
                self.assertEqual(case.arguments,args)
                self.assertEqual(case.prompt,prompt)
                self.assertEqual(case.expected,answer)

    def test_source_mutation_fails_full_inventory(self):
        wrong=list(self.cases)
        wrong[0]=replace(wrong[0],case_id=self.cases[1].case_id)
        self.assertFalse(verify_exact(tuple(wrong)))

    def test_missing_case_fails_full_inventory(self):
        self.assertFalse(verify_exact(self.cases[:-1]))

    def test_critical_count_is_exact(self):
        expected=len(CRITICAL)*24
        self.assertEqual(sum(x.severity=="critical" for x in self.cases),expected)

    def test_source_not_equivalent_to_native_execution(self):
        self.assertFalse(inventory()["native_inference_executed"])
        self.assertFalse(inventory()["release_certified"])


if __name__=="__main__":
    unittest.main()
