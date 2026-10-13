"""Real-source workpack regression suite: plans do not become authority."""
from __future__ import annotations

from hashlib import sha256
import unittest

from skeleton.ai.game_builder.jeeves_appwide_fabric import (
    JeevesAppwideError, JeevesAppwideRuntime)
from skeleton.ai.game_builder.jeeves_deathmarch_workpacks import (
    JeevesWorkpackDirector, _limited_excerpt)
from tests.test_game_builder_jeeves_completion_census import CompletionCensusTests


class DeathmarchWorkpacksTests(unittest.TestCase):
    def setUp(self):
        self.fixture = CompletionCensusTests(
            "test_sources_and_declared_maturity_never_certify_product")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.docs = self.fixture.docs
        self.inv = self.fixture.inv
        self.director = JeevesWorkpackDirector(self.inv)

    def refresh(self):
        self.fixture.flush()
        self.inv.scan()

    def test_waves_keep_dependencies_across_owner_isolated_stage(self):
        services = self.docs["skeleton/app/manifest.json"]["services"]
        services[0]["depends_on"] = ["skeleton"]
        self.refresh()
        result = self.director.waves(max_parallel=3, limit=20)
        self.assertEqual(result["completed_tasks"], 0)
        self.assertTrue(result["all_waves_require_execution_authority"])
        slots = {}
        for wave in result["waves"]:
            self.assertEqual(len(wave["owners"]), len(set(wave["owners"])))
            self.assertLessEqual(len(wave["task_ids"]), 3)
            self.assertFalse(wave["executor_leases_acquired"])
            self.assertFalse(wave["runtime_tasks_started"])
            slots.update({name: wave["wave"] for name in wave["task_ids"]})
        self.assertLess(slots["APP-SERVICE-skeleton"],
                        slots["APP-SERVICE-backend"])
        self.assertEqual(result, self.director.waves(max_parallel=3, limit=20))

    def test_waves_pagination_and_bounded_capacity(self):
        a = self.director.waves(limit=1, max_parallel=1)
        self.assertIsNotNone(a["next_offset"])
        b = self.director.waves(offset=a["next_offset"],
                                limit=1, max_parallel=1)
        self.assertEqual(b["waves"][0]["wave"], 1)
        for params in ({"limit": 0}, {"offset": True},
                       {"max_parallel": 0}, {"max_parallel": 99}):
            with self.subTest(params=params), self.assertRaises(JeevesAppwideError):
                self.director.waves(**params)

    def test_directory_source_context_is_real_bounded_and_unapproved(self):
        # Service owner is a directory; no fabricated source owner is needed.
        pack = self.director.workpack(task_ids=["APP-SERVICE-backend"],
                                       source_bytes=512, total_bytes=2048)
        self.assertTrue(pack["operator_must_approve_source_changes"])
        self.assertFalse(pack["code_executed"])
        self.assertFalse(pack["source_mutated"])
        self.assertFalse(pack["tests_executed"])
        self.assertEqual(pack["automatic_completion_claims"], 0)
        self.assertLessEqual(pack["context_bytes"], 2048)
        self.assertEqual(pack["task_ids"], ["APP-SERVICE-backend"])
        self.assertEqual(pack["source_count"], 1)
        entry = pack["sources"][0]
        self.assertEqual(entry["path"], "backend/server.py")
        self.assertEqual(entry["sha256"],
                         sha256(b"# backend runtime stub, not proof\n").hexdigest())
        self.assertTrue(entry["directory_sample_not_owner_proof"])
        self.assertTrue(entry["code_was_not_executed"])
        self.assertTrue(pack["tasks"][0]["source_context_found"])
        self.assertFalse(pack["tasks"][0]["ready_to_modify_source"])

    def test_empty_context_is_explicit_not_false_feature_completion(self):
        packet = self.director.workpack(task_ids=["AI-CAP-assistant.text"])
        self.assertFalse(packet["tasks"][0]["source_context_found"])
        self.assertTrue(packet["tasks"][0][
            "unlinked_or_missing_context_requires_human_selection"])
        self.assertTrue(packet["source_truncated_or_missing"])

    def test_changed_file_to_owner_and_milestone_frontier(self):
        overview = self.director.change_frontier(paths=["backend/server.py"])
        self.assertFalse(overview["source_files_mutated"])
        self.assertTrue(overview["directory_scope_is_not_runtime_dependency_proof"])
        self.assertEqual(overview["unmapped_paths"], [])
        ids = {x["task_id"] for x in overview["affected_milestones"]}
        self.assertIn("APP-SERVICE-backend", ids)
        self.assertFalse(any(x["live_runtime_impact_verified"]
                             for x in overview["affected"]))
        sha = overview["changed_paths"][0]["content_sha256"]
        self.assertEqual(sha, sha256(b"# backend runtime stub, not proof\n").hexdigest())
        self.assertEqual(overview, self.director.change_frontier(
            paths=["backend/server.py"]))

    def test_unlinked_path_is_unassessed_not_safe(self):
        self.fixture.put("unrelated.txt", "unmapped original readme\n")
        self.inv.scan()
        report = self.director.change_frontier(paths=["unrelated.txt"])
        self.assertEqual(report["unmapped_paths"], ["unrelated.txt"])
        self.assertTrue(report["unmapped_means_unassessed_not_safe"])
        self.assertEqual(report["affected_milestone_count"], 0)

    def test_private_source_paths_and_out_of_scope_ids_refused(self):
        with self.assertRaises(JeevesAppwideError):
            self.director.change_frontier(paths=["machine/.env"])
        with self.assertRaises(JeevesAppwideError):
            self.director.change_frontier(paths=["../../etc/passwd"])
        with self.assertRaises(JeevesAppwideError):
            self.director.workpack(task_ids=["AI-CAP-unknown"])
        with self.assertRaises(JeevesAppwideError):
            self.director.workpack(task_ids=["APP-SERVICE-backend"] * 2)

    def test_no_boolean_tricks_on_source_bounds_or_total_budget(self):
        for opts in ({"source_bytes": True}, {"total_bytes": False},
                     {"source_bytes": 1}, {"max_sources": 0},
                     {"max_sources": 100000}):
            with self.subTest(opts=opts), self.assertRaises(JeevesAppwideError):
                self.director.workpack(task_ids=["APP-SERVICE-backend"], **opts)

    def test_source_receipt_conflicts_rejected_after_same_size_mutation(self):
        before = self.director.workpack(
            task_ids=["APP-SERVICE-backend"])
        self.fixture.put("backend/server.py", "# backend runtime mock, not proof\n")
        self.inv.scan()
        after = self.director.workpack(
            task_ids=["APP-SERVICE-backend"])
        self.assertNotEqual(before["digest"], after["digest"])
        self.assertNotEqual(before["sources"][0]["sha256"],
                            after["sources"][0]["sha256"])

    def test_utf8_excerpts_are_bounded_on_code_points(self):
        original = "æ" * 1000
        clipped, shortened, observed_bytes = _limited_excerpt(original, 513)
        self.assertTrue(shortened)
        self.assertLessEqual(len(clipped.encode("utf-8")), 513)
        self.assertEqual(observed_bytes, 2000)
        self.assertFalse("\ufffd" in clipped)
        self.assertEqual(_limited_excerpt("small\n", 1024),
                         ("small\n", False, 6))

    def test_existing_runtime_actions_are_gated_and_inert(self):
        runtime = JeevesAppwideRuntime(self.inv)
        wave = runtime.invoke("ai.workwaves", {"max_parallel": 2})["result"]
        self.assertEqual(wave["completed_tasks"], 0)
        packet = runtime.invoke("ai.workpack", {
            "task_ids": ["APP-SERVICE-backend"]})["result"]
        self.assertFalse(packet["code_executed"])
        change = runtime.invoke("ai.change_frontier", {
            "paths": ["backend/server.py"]})["result"]
        self.assertTrue(change["unmapped_means_unassessed_not_safe"])


if __name__ == "__main__":
    unittest.main()
