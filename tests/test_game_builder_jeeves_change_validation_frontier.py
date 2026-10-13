"""Jeeves changed source to canonical declared focused validation suite."""
from __future__ import annotations

from hashlib import sha256
import unittest

from skeleton.ai.game_builder.jeeves_appwide_fabric import (
    JeevesAppwideError, JeevesAppwideRuntime)
from skeleton.ai.game_builder.jeeves_change_validation_frontier import (
    JeevesChangeValidationFrontier)
from tests.test_game_builder_jeeves_completion_census import CompletionCensusTests


class ChangeValidationFrontierTests(unittest.TestCase):
    def setUp(self):
        self.fixture = CompletionCensusTests(
            "test_sources_and_declared_maturity_never_certify_product")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.inv = self.fixture.inv
        self.docs = self.fixture.docs
        self.candidate = "backend/server.py"
        self.test_path = "tests/test_backend_server.py"
        self.eval_path = ".github/workflows/backend-quality.yml"
        self.fixture.put(self.test_path,
                         "def test_server_status(): assert True\n")
        self.fixture.put(self.eval_path,
                         "name: Backend Quality\non: workflow_dispatch\n")
        volume = self.docs["machine/ai_master_plan.json"]["volumes"][0]
        volume["implementation_paths"] = ["backend"]
        volume["tests"] = [self.test_path]
        volume["evaluations"] = [self.eval_path]
        self.refresh()
        self.matrix = JeevesChangeValidationFrontier(self.inv)

    def refresh(self):
        self.fixture.flush()
        self.inv.scan()

    def test_changed_source_maps_directory_owner_and_focused_checks(self):
        report = self.matrix.overview(paths=[self.candidate])
        self.assertEqual(report["impacted_declared_volumes"], 1)
        self.assertEqual(report["candidate_validation_items"], 2)
        self.assertEqual(report["unmapped_changed_paths"], [])
        self.assertTrue(report["mandatory_release_checks_must_still_run"])
        self.assertFalse(report["release_qualified"])
        self.assertTrue(report["all_tests_unexecuted"])
        self.assertTrue(report["unknown_impact_is_not_safety"])
        self.assertEqual(report["source_revisions_proposed_or_written"], 0)
        self.assertTrue(report["changed_sources"][0]["source_content_verified"])
        page = self.matrix.page(paths=[self.candidate], limit=5,
                                expected_frontier_digest=report["digest"])
        self.assertEqual({x["type"] for x in page["validation_candidates"]},
                         {"test", "evaluation"})
        self.assertEqual({x["path"] for x in page["validation_candidates"]},
                         {self.test_path, self.eval_path})
        self.assertTrue(all(not x["source_executed"] and
                            not x["exact_head_ci_verified"]
                            for x in page["validation_candidates"]))

    def test_shared_test_deduplicated_across_multiple_volumes(self):
        other = self.docs["machine/ai_master_plan.json"]["volumes"][1]
        other["implementation_paths"] = ["backend/server.py"]
        other["tests"] = [self.test_path]
        other["evaluations"] = [self.eval_path]
        self.refresh()
        result = self.matrix.overview(paths=[self.candidate])
        self.assertEqual(result["impacted_declared_volumes"], 2)
        self.assertEqual(result["candidate_validation_items"], 2)
        page = self.matrix.page(paths=[self.candidate])
        self.assertEqual({tuple(x["declared_by_volumes"])
                          for x in page["validation_candidates"]},
                         {("vol:VOL-000", "vol:VOL-001")})

    def test_unmapped_is_not_safe_or_proven_unchanged(self):
        self.fixture.put("frontend/unknown.tsx", "export const unknown = 1;\n")
        self.inv.scan()
        result = self.matrix.overview(paths=["frontend/unknown.tsx"])
        self.assertEqual(result["unmapped_changed_paths"],
                         ["frontend/unknown.tsx"])
        self.assertEqual(result["impacted_declared_volumes"], 0)
        self.assertEqual(result["candidate_validation_items"], 0)
        self.assertFalse(result["release_qualified"])

    def test_missing_test_evaluation_not_forged(self):
        volume = self.docs["machine/ai_master_plan.json"]["volumes"][0]
        volume["tests"] = ["tests/missing_test.py"]
        volume["evaluations"] = [".github/workflows/missing.yml"]
        self.refresh()
        report = self.matrix.overview(paths=[self.candidate])
        self.assertEqual(report["candidate_validation_items"], 0)
        self.assertEqual({x["gap"] for x in
                          report["missing_static_test_or_evaluation_refs"]},
                         {"no_accessible_declared_test",
                          "no_accessible_declared_evaluation"})
        self.assertFalse(report["release_qualified"])

    def test_cursor_optimism_detects_changed_source_contracts(self):
        prior = self.matrix.overview(paths=[self.candidate])
        self.docs["machine/ai_master_plan.json"]["volumes"][0]["title"] = "Changed"
        self.refresh()
        with self.assertRaises(JeevesAppwideError):
            self.matrix.page(paths=[self.candidate],
                             expected_frontier_digest=prior["digest"])

    def test_invalid_sources_duplicates_and_paging_fail_closed(self):
        with self.assertRaises(JeevesAppwideError):
            self.matrix.overview(paths=[])
        with self.assertRaises(JeevesAppwideError):
            self.matrix.overview(paths=[self.candidate, self.candidate])
        with self.assertRaises(JeevesAppwideError):
            self.matrix.overview(paths=["machine/.env"])
        with self.assertRaises(JeevesAppwideError):
            self.matrix.overview(paths=["../../etc/shadow"])
        with self.assertRaises(JeevesAppwideError):
            self.matrix.overview(paths=["unseen.py"])
        for options in ({"offset": True}, {"limit": True}, {"limit": 0},
                        {"offset": -1}, {"limit": 1000}):
            with self.subTest(options=options), self.assertRaises(JeevesAppwideError):
                self.matrix.page(paths=[self.candidate], **options)

    def test_jeeves_registered_action_is_read_only(self):
        runtime = JeevesAppwideRuntime(self.inv)
        result = runtime.invoke("ai.validation.frontier", {
            "paths": [self.candidate]})
        self.assertTrue(result["read_only_or_review_only"])
        self.assertEqual(result["result"]["candidate_validation_items"], 2)
        page = runtime.invoke("ai.validation.frontier.page", {
            "paths": [self.candidate], "limit": 1})["result"]
        self.assertEqual(len(page["validation_candidates"]), 1)
        self.assertTrue(page["user_approval_and_ci_authority_not_inferred"])


if __name__ == "__main__":
    unittest.main()
