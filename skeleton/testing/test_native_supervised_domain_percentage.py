"""Original native-SFT percentage challenge admission and independent oracle."""
from __future__ import annotations
from dataclasses import replace
import unittest

from skeleton.ai.runtime.operational_ai.native_supervised.challenge_catalog import (
    iter_challenges,
)
from skeleton.ai.runtime.operational_ai.native_supervised.challenge_schema import (
    Challenge,
)
from skeleton.ai.runtime.operational_ai.native_supervised.challenge_oracle import (
    synthesize,
)
from skeleton.ai.runtime.operational_ai.native_supervised.canonical import encode
from skeleton.ai.runtime.operational_ai.native_supervised.errors import SupervisedRejected


class TestPercentageNativeChallenges(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases=tuple(case for case in iter_challenges()
                        if case.domain=="percentage")

    def test_all_24_original_cases_are_present(self):
        self.assertEqual(len(self.cases),24)
        self.assertEqual({c.ordinal for c in self.cases},set(range(1,25)))
        self.assertEqual(len({c.case_id for c in self.cases}),24)

    def test_authored_answer_matches_independent_oracle(self):
        for case in self.cases:
            with self.subTest(case=case.case_id):
                args,prompt,answer=synthesize(case.domain,case.ordinal)
                self.assertEqual(case.arguments,args)
                self.assertEqual(case.prompt,prompt)
                self.assertEqual(case.expected,answer)

    def test_all_cases_have_stable_canonical_source_sha(self):
        self.assertEqual(len({c.sha256 for c in self.cases}),24)
        self.assertEqual(len({c.prompt_sha256 for c in self.cases}),24)
        for case in self.cases:
            with self.subTest(case=case.case_id):
                self.assertEqual(Challenge.parse(encode(case.record())),case)

    def test_corrupt_answer_is_denied_before_inference(self):
        for case in self.cases[:3]:
            with self.subTest(case=case.case_id):
                with self.assertRaises(SupervisedRejected):
                    replace(case,expected=case.expected+" falsified")

    def test_corrupt_prompt_is_denied_before_inference(self):
        case=self.cases[0]
        with self.assertRaises(SupervisedRejected):
            replace(case,prompt=case.prompt+" injected override")

    def test_missing_provenance_is_not_accepted(self):
        with self.assertRaises(SupervisedRejected):
            replace(self.cases[0],provenance="unverified_external")

    def test_training_rights_are_not_implicitly_granted(self):
        self.assertTrue(all(c.purpose=="offline_native_sft_evaluation"
                            for c in self.cases))
        self.assertTrue(all(c.license_id=="skeleton_original"
                            for c in self.cases))
        self.assertFalse(any(hasattr(c,"training_permitted") for c in self.cases))

    def test_expected_severity_is_source_fixed(self):
        severity="medium"
        self.assertEqual({c.severity for c in self.cases},{severity})
        with self.assertRaises(SupervisedRejected):
            replace(self.cases[0],severity="medium" if severity=="critical" else "critical")

    def test_case_ids_cannot_be_rebound(self):
        with self.assertRaises(SupervisedRejected):
            replace(self.cases[0],case_id="percentage_99")

    def test_no_fixture_claims_model_quality(self):
        for case in self.cases:
            self.assertNotIn("model_passed",case.record())
            self.assertNotIn("actual_output",case.record())


if __name__=="__main__":
    unittest.main()
