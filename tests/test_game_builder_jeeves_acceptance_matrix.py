"""Candidate product acceptance links are truthful, bounded and source-bound."""
from __future__ import annotations

from copy import deepcopy
import json
import unittest

from skeleton.ai.game_builder.jeeves_appwide_fabric import (
    JeevesAppwideError, JeevesAppwideRuntime)
from skeleton.ai.game_builder.jeeves_acceptance_matrix import JeevesAcceptanceTestMatrix
from tests.test_game_builder_jeeves_completion_census import CompletionCensusTests


class AcceptanceMatrixTests(unittest.TestCase):
    def setUp(self):
        self.fixture = CompletionCensusTests(
            "test_sources_and_declared_maturity_never_certify_product")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.inv = self.fixture.inv
        self.scope = {
            "schema":"skeleton.ai.app_completion_scope.v1",
            "families":[{"id":"F%02d" % n, "title":"Family"}
                        for n in range(1,43)],
        }
        self.doc = {
            "schema":"skeleton.ai.app_acceptance_test_matrix.v1",
            "parent_scope":"machine/app_completion_scope.json",
            "stage":"implementation_test",
            "runner_mode":"unittest_module_exact_head",
            "policies": {
                name: True for name in (
                    "requires_real_test_execution","exact_commit_required",
                    "source_test_sha_receipts_required",
                    "no_success_inference_from_file_presence",
                    "matrix_does_not_verify_end_to_end_user_journey",
                    "automated_model_or_source_promotion_forbidden",
                    "unmapped_families_remain_unknown",
                )
            },
            "bindings":[{
                "family_id":"F11",
                "scope":"targeted_regression_subset",
                "independent_acceptance_question":
                    "Does the real Jeeves path block unauthorized appwide actions?",
                "unittest_modules":["tests.test_game_builder_sample_acceptance"],
                "workflow_hint":"Jeeves Story Canon Production",
                "product_release_qualified":False,
            }],
        }
        self.path = "tests/test_game_builder_sample_acceptance.py"
        self.source = (
            "import unittest\n"
            "class TrueBoundary(unittest.TestCase):\n"
            "    def test_accepts_real_value(self): self.assertEqual(2,2)\n"
            "    def test_does_not_leak(self): self.assertTrue(True)\n"
        )
        self.fixture.put(self.path,self.source)
        self.refresh()
        self.audit = JeevesAcceptanceTestMatrix(self.inv)

    def refresh(self):
        self.fixture.put("machine/app_completion_scope.json",
                         json.dumps(self.scope,sort_keys=True))
        self.fixture.put("machine/app_acceptance_test_matrix.json",
                         json.dumps(self.doc,sort_keys=True))
        self.inv.scan()

    def test_one_family_two_real_test_functions_no_qualification(self):
        report = self.audit.overview()
        self.assertEqual(report["family_denominator"],42)
        self.assertEqual(report["curated_test_family_count"],1)
        self.assertEqual(len(report["families_without_curated_tests"]),41)
        self.assertEqual(report["unique_test_module_count"],1)
        self.assertEqual(report["scheduled_test_module_count"],1)
        self.assertEqual(report["ci_smoke_family_count"],1)
        self.assertEqual(report["discovery_only_family_count"],0)
        self.assertEqual(report["unique_static_test_case_count"],2)
        self.assertEqual(report["tests_executed_by_this_reader"],0)
        self.assertIsNone(report["exact_head_passed_from_source_scan"])
        self.assertTrue(report["source_coverage_is_not_accepted_test_evidence"])
        self.assertEqual(report,self.audit.overview())

    def test_discovery_only_expands_coverage_without_executing_any_more_modules(self):
        candidate = deepcopy(self.doc["bindings"][0])
        candidate["family_id"] = "F14"
        candidate["execution_tier"] = "discovery_only"
        self.doc["bindings"].append(candidate)
        self.refresh()
        summary = self.audit.overview()
        self.assertEqual(summary["curated_test_family_count"], 2)
        self.assertEqual(summary["ci_smoke_family_count"], 1)
        self.assertEqual(summary["discovery_only_family_count"], 1)
        self.assertEqual(summary["unique_test_module_count"], 1)
        self.assertEqual(summary["scheduled_test_module_count"], 1)
        self.assertEqual(summary["selected_modules"],
                         ["tests.test_game_builder_sample_acceptance"])
        discovered = self.audit.page()["families"]
        self.assertEqual([v["execution_tier"] for v in discovered],
                         ["ci_smoke", "discovery_only"])
        self.assertTrue(all(row["independent_execution_verified"] is None
                            for row in discovered))

    def test_pytest_runner_is_separate_and_requires_actual_independent_execution(self):
        candidate=deepcopy(self.doc["bindings"][0])
        candidate["family_id"]="F17"
        candidate["execution_tier"]="pytest_smoke"
        self.doc["bindings"].append(candidate)
        self.refresh()
        report=self.audit.overview()
        self.assertEqual(report["curated_test_family_count"],2)
        self.assertEqual(report["ci_smoke_family_count"],1)
        self.assertEqual(report["pytest_smoke_family_count"],1)
        self.assertEqual(report["scheduled_test_module_count"],1)
        self.assertEqual(report["scheduled_pytest_module_count"],1)
        self.assertEqual(report["selected_modules"],
                         ["tests.test_game_builder_sample_acceptance"])
        self.assertEqual(report["pytest_selected_modules"],
                         ["tests.test_game_builder_sample_acceptance"])
        self.assertIsNone(report["exact_head_passed_from_source_scan"])
        self.assertEqual(report["tests_executed_by_this_reader"],0)

    def test_invalid_execution_tier_never_increases_verified_coverage(self):
        self.doc["bindings"][0]["execution_tier"] = "autopromote"
        self.refresh()
        with self.assertRaises(JeevesAppwideError):
            self.audit.overview()

    def test_missing_families_page_and_candidate_distinction(self):
        report=self.audit.overview()
        active=self.audit.page(expected_matrix_digest=report["digest"])
        self.assertEqual(active["total_matches"],1)
        self.assertEqual(active["families"][0]["targeted_cases_declared"],2)
        self.assertIsNone(active["families"][0]["independent_execution_verified"])
        missing=self.audit.page(only_unmapped=True,limit=20)
        self.assertEqual(missing["total_matches"],41)
        self.assertEqual(missing["next_offset"],20)
        self.assertTrue(all(item["missing_curated_tests"] for item in missing["families"]))

    def test_real_test_identity_change_invalidates_acceptance_projection(self):
        before=self.audit.overview()
        self.fixture.put(self.path,self.source.replace(
            "test_does_not_leak","test_does_not_read"))
        self.inv.scan()
        after=self.audit.overview()
        self.assertNotEqual(before["digest"],after["digest"])
        self.assertNotEqual(before["module_source_receipts"][0]["sha256"],
                            after["module_source_receipts"][0]["sha256"])
        with self.assertRaises(JeevesAppwideError):
            self.audit.page(expected_matrix_digest=before["digest"])

    def test_no_test_functions_cannot_count_as_acceptance_candidate(self):
        self.fixture.put(self.path,"def setup_only(): return 1\n")
        self.inv.scan()
        with self.assertRaises(JeevesAppwideError):
            self.audit.overview()

    def test_duplicate_module_family_and_traversal_fail_closed(self):
        self.doc["bindings"].append(deepcopy(self.doc["bindings"][0]))
        self.refresh()
        with self.assertRaises(JeevesAppwideError):
            self.audit.overview()
        self.doc["bindings"].pop()
        self.doc["bindings"][0]["unittest_modules"]=["tests.evil.__main__"]
        self.refresh()
        with self.assertRaises(JeevesAppwideError):
            self.audit.overview()
        self.doc["bindings"][0]["unittest_modules"]=[
            "tests.test_game_builder_sample_acceptance"]
        self.doc["bindings"][0]["family_id"]="F43"
        self.refresh()
        with self.assertRaises(JeevesAppwideError):
            self.audit.overview()

    def test_false_runtime_signoff_and_test_policy_downgrade_rejected(self):
        self.doc["bindings"][0]["product_release_qualified"]=True
        self.refresh()
        with self.assertRaises(JeevesAppwideError):
            self.audit.overview()
        self.doc["bindings"][0]["product_release_qualified"]=False
        self.doc["policies"]["requires_real_test_execution"]=False
        self.refresh()
        with self.assertRaises(JeevesAppwideError):
            self.audit.overview()

    def test_typed_pages_and_changed_selection_guard(self):
        for kwargs in ({"offset":True},{"limit":True},{"offset":-1},
                       {"limit":0},{"limit":999},{"only_unmapped":"yes"}):
            with self.subTest(kwargs=kwargs),self.assertRaises(JeevesAppwideError):
                self.audit.page(**kwargs)
        original=self.audit.overview()
        self.doc["bindings"][0]["workflow_hint"]="Altered hint"
        self.refresh()
        with self.assertRaises(JeevesAppwideError):
            self.audit.overview(expected_matrix_sha256=original["matrix_sha256"])

    def test_explicit_jeeves_read_only_boundary(self):
        runtime=JeevesAppwideRuntime(self.inv)
        outcome=runtime.invoke("ai.product.tests",{})
        self.assertTrue(outcome["read_only_or_review_only"])
        self.assertEqual(outcome["result"]["unique_static_test_case_count"],2)
        page=runtime.invoke("ai.product.tests.page",{"only_unmapped":True,"limit":1})
        self.assertTrue(page["result"]["unverified_tests_not_counted_as_accepted"])


if __name__ == "__main__":
    unittest.main()
