"""Independent targeted-regression evidence rollup cannot become feature signoff."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.ai.game_builder.jeeves_appwide_fabric import JeevesAppwideError, digest
from skeleton.ai.game_builder.jeeves_acceptance_rollup import combine


class IndependentTargetedAcceptanceRollupTests(unittest.TestCase):
    def setUp(self):
        self.head = "a"*40
        self.families = ["F%02d"%i for i in range(1,43)]
        self.junit = self._proof(
            "skeleton.ai.app_acceptance_verified_ci.v1",
            101, self.families[:17])
        self.pytest = self._proof(
            "skeleton.ai.app_pytest_acceptance_verified_ci.v1",
            102, self.families[17:])

    def _proof(self, schema, run, family):
        body = {
            "schema": schema,
            "repository": "Apeloff1/Skeleton",
            "verified_git_head": self.head,
            "run_id": run,
            "run_attempt": 1,
            "independent_ci_execution_verified": True,
            "release_device_qualified": False,
            "full_app_completion_percent": None,
            "verified_os": [
                {"os": "Linux", "job_id":run*10},
                {"os": "Windows", "job_id":run*10+1},
            ],
            "family_denominator": 42,
        }
        if schema.endswith("pytest_acceptance_verified_ci.v1"):
            body.update({
                "pytest_targeted_families": family,
                "pytest_targeted_family_count": len(family),
                "whole_feature_acceptance_admitted": 0,
                "source_subsets_are_not_user_journeys": True,
            })
        else:
            body.update({
                "targeted_regression_subsets_verified_for_families": family,
                "targeted_family_subset_count": len(family),
                "complete_family_stage_qualifications_admitted": 0,
                "targeted_subset_is_not_full_feature_implementation_test_acceptance":True,
            })
        return {**body, "digest": digest(body)}

    def rollup(self):
        return combine(
            head=self.head,
            expected_families=self.families,
            unittest_proof=self.junit,
            pytest_proof=self.pytest,
            reviewed_matrix_sha256="b"*64,
            reviewed_scope_sha256="c"*64,
        )

    def test_real_ci_verified_42_targeted_subsets_still_not_product_completion(self):
        receipt = self.rollup()
        self.assertEqual(receipt["family_denominator"], 42)
        self.assertEqual(receipt["verified_targeted_regression_subset_families"], 42)
        self.assertTrue(receipt["all_42_targeted_subsets_verified"])
        self.assertEqual(receipt["independent_targeted_subset_pct"], 100.0)
        self.assertEqual(receipt["independent_original_GitHub_runs_verified"], 2)
        self.assertEqual(receipt["os_job_receipts_verified"], 4)
        self.assertEqual(receipt["actual_complete_family_release_qualifications"], 0)
        self.assertEqual(receipt["independent_end_to_end_user_journeys_in_this_receipt"], 0)
        self.assertFalse(receipt["trained_model_quality_qualified"])
        self.assertFalse(receipt["device_install_or_game_export_qualified"])
        self.assertIsNone(receipt["full_app_completion_percent"])
        self.assertTrue(receipt["each_targeted_subset_is_not_full_feature_acceptance"])
        self.assertEqual(receipt, self.rollup())

    def test_partial_verified_CI_reports_missing_targeted_regression_families(self):
        self.pytest["pytest_targeted_families"] = self.families[17:31]
        self.pytest["pytest_targeted_family_count"] = 14
        self.pytest["digest"] = digest({
            k: v for k, v in self.pytest.items() if k != "digest"})
        report=self.rollup()
        self.assertEqual(report["verified_targeted_regression_subset_families"],31)
        self.assertEqual(report["independent_targeted_subset_pct"],73.81)
        self.assertEqual(report["unverified_targeted_regression_subset_ids"],
                         self.families[31:])
        self.assertFalse(report["all_42_targeted_subsets_verified"])
        self.assertIsNone(report["full_app_completion_percent"])

    def test_overlapping_or_noncanonical_family_names_denied(self):
        original=deepcopy(self.pytest)
        for changed in (["F17"] + self.families[18:],
                        ["F99"] + self.families[18:],
                        ["F001"] + self.families[18:],
                        ["F18","F18"] + self.families[19:]):
            self.pytest=deepcopy(original)
            self.pytest["pytest_targeted_families"] = changed
            self.pytest["pytest_targeted_family_count"] = len(changed)
            self.pytest["digest"] = digest({
                k: v for k, v in self.pytest.items() if k != "digest"})
            with self.subTest(changed=changed),self.assertRaises(JeevesAppwideError):
                self.rollup()
        self.pytest=original

    def test_untrusted_digest_or_wrong_head_denied(self):
        for field, bad in (
            ("verified_git_head","d"*40),
            ("digest","f"*64),
            ("run_id",101),
            ("independent_ci_execution_verified",False),
            ("release_device_qualified",True),
            ("full_app_completion_percent",100.0),
            ("schema","other.schema.v1"),
            ("verified_os",[{"os":"Linux","job_id":23}]),
        ):
            original=deepcopy(self.pytest[field])
            self.pytest[field]=bad
            with self.subTest(field=field),self.assertRaises(JeevesAppwideError):
                self.rollup()
            self.pytest[field]=original

    def test_same_GitHub_run_id_cannot_prove_both_test_modes(self):
        self.pytest["run_id"] = self.junit["run_id"]
        self.pytest["digest"] = digest({
            k: v for k, v in self.pytest.items() if k != "digest"})
        with self.assertRaises(JeevesAppwideError):
            self.rollup()

    def test_unapproved_family_denominator_and_source_sha_rejected(self):
        self.families = self.families[:41]
        with self.assertRaises(JeevesAppwideError):
            self.rollup()
        self.families = ["F%02d"%i for i in range(1,43)]
        for invalid in ("notsha", "A"*64, 1, None):
            with self.subTest(invalid=invalid),self.assertRaises(JeevesAppwideError):
                combine(
                    head=self.head, expected_families=self.families,
                    unittest_proof=self.junit, pytest_proof=self.pytest,
                    reviewed_matrix_sha256=invalid,
                    reviewed_scope_sha256="c"*64,
                )


if __name__ == "__main__":
    unittest.main()
