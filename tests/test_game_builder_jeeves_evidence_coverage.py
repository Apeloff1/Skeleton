"""Static evidence audit: anti-signature-laundering and source-scope tests."""
from __future__ import annotations

import unittest
from copy import deepcopy

from skeleton.ai.game_builder.jeeves_appwide_fabric import (
    AppwideInventory, JeevesAppwideError, JeevesAppwideRuntime)
from skeleton.ai.game_builder.jeeves_evidence_coverage import JeevesEvidenceCoverage
from tests.test_game_builder_jeeves_completion_census import CompletionCensusTests


class EvidenceCoverageTests(unittest.TestCase):
    def setUp(self):
        self.fixture = CompletionCensusTests(
            "test_sources_and_declared_maturity_never_certify_product")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.inv = self.fixture.inv
        self.docs = self.fixture.docs
        self.cov = JeevesEvidenceCoverage(self.inv)

    def refresh(self):
        self.fixture.flush()
        self.inv.scan()

    def test_coverage_is_static_never_tests_passed(self):
        report = self.cov.overview()
        self.assertEqual(report["total_volumes"], 2)
        self.assertEqual(report["static_facet_complete"], 0)
        self.assertIsNone(report["executable_test_pass_count"])
        self.assertIsNone(report["real_app_capability_coverage"])
        self.assertFalse(report["asserted_release_qualified"])
        self.assertTrue(report["declared_evidence_is_not_executable_qualification"])
        self.assertEqual(report, self.cov.overview())

    def test_refs_are_counted_only_with_actual_safe_paths(self):
        volume = self.docs["machine/ai_master_plan.json"]["volumes"][0]
        volume["implementation_paths"] = ["backend/server.py",
                                           "backend/server.py",
                                           "backend/missing.py",
                                           "machine/.env"]
        volume["tests"] = ["backend/server.py"]
        volume["evaluations"] = ["backend/server.py"]
        self.refresh()
        page = self.cov.page(limit=2)
        item = next(x for x in page["volumes"] if x["id"] == "VOL-000")
        impl = item["dimensions"]["implementation"]
        self.assertEqual(impl["declared"], 3)
        self.assertEqual(impl["present"], 1)
        self.assertEqual(impl["unavailable_or_restricted"], 2)
        self.assertIn("incomplete_implementation_reference_coverage",
                      item["static_evidence_gaps"])
        self.assertTrue(all(v["executed_and_passed"] is None
                            for v in item["dimensions"].values()))
        self.assertNotIn("machine/.env", str(page))

    def test_complete_file_presence_not_misrepresented_as_model_quality(self):
        for volume in self.docs["machine/ai_master_plan.json"]["volumes"]:
            for key in ("implementation_paths", "tests", "evaluations"):
                volume[key] = ["backend/server.py"]
            volume["enterprise_grade_state"] = "enterprise_qualified"
        self.refresh()
        report = self.cov.overview()
        self.assertEqual(report["static_facet_complete"], 2)
        self.assertFalse(report["asserted_release_qualified"])
        self.assertIsNone(report["executable_test_pass_count"])
        rows = self.cov.page()["volumes"]
        self.assertTrue(all(not row["enterprise_qualified"] for row in rows))
        self.assertTrue(all(row["runtime_tests_verified"] is None for row in rows))

    def test_pagination_filter_cursor_and_stale_identity(self):
        overview = self.cov.overview()
        one = self.cov.page(limit=1, expected_coverage_digest=overview["digest"])
        self.assertEqual(one["next_offset"], 1)
        self.assertEqual(len(self.cov.page(offset=1, limit=1)["volumes"]), 1)
        self.assertEqual(self.cov.page(offset=2)["volumes"], [])
        gaps = self.cov.page(only_gaps=True)
        self.assertEqual(gaps["total_matches"], 2)
        self.docs["machine/ai_master_plan.json"]["volumes"][0][
            "implementation_status"] = "hardened"
        self.refresh()
        with self.assertRaises(JeevesAppwideError):
            self.cov.page(expected_coverage_digest=overview["digest"])

    def test_untrusted_bogus_references_never_get_executed(self):
        volume = self.docs["machine/ai_master_plan.json"]["volumes"][0]
        volume["tests"] = ["../../etc/shadow", ".env", "secrets.txt",
                            "backend/missing_test.py"]
        self.refresh()
        page = self.cov.page()
        self.assertIn("no_present_test_references",
                      page["volumes"][0]["static_evidence_gaps"])
        self.assertNotIn("shadow", str(page))
        self.assertTrue(page["no_test_or_signature_promotion_performed"])

    def test_invalid_source_schema_strictly_fail_closed(self):
        vol = self.docs["machine/ai_master_plan.json"]["volumes"][0]
        vol["tests"] = "unverified_test.py"
        self.refresh()
        with self.assertRaises(JeevesAppwideError):
            self.cov.overview()
        vol["tests"] = ["backend/server.py"]
        vol["key"] = "VOL-001"
        self.refresh()
        with self.assertRaises(JeevesAppwideError):
            self.cov.overview()

    def test_boolean_limits_and_invalid_page_filters_fail_closed(self):
        for options in ({"limit": 0}, {"offset": -1}, {"limit": True},
                        {"offset": True}, {"limit": 999}, {"only_gaps": 1},
                        {"only_gaps": "yes"}):
            with self.subTest(options=options):
                with self.assertRaises(JeevesAppwideError):
                    self.cov.page(**options)

    def test_registered_read_only_jeeves_coverage(self):
        runtime = JeevesAppwideRuntime(self.inv)
        result = runtime.invoke("ai.coverage", {})
        self.assertEqual(result["result"]["total_volumes"], 2)
        self.assertTrue(result["read_only_or_review_only"])
        rows = runtime.invoke("ai.coverage.page", {"limit": 1})["result"]
        self.assertEqual(len(rows["volumes"]), 1)
        self.assertTrue(rows["acceptance_requires_exact_head_independent_evidence"])


if __name__ == "__main__":
    unittest.main()
