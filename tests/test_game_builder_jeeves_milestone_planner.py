"""Executable positive and negative acceptance for Jeeves milestone DAG."""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.ai.game_builder.jeeves_appwide_fabric import (
    JeevesAppwideError, JeevesAppwideRuntime)
from skeleton.ai.game_builder.jeeves_milestone_planner import (
    JeevesMilestonePlanner, _topological_ids)
from tests.test_game_builder_jeeves_completion_census import CompletionCensusTests


class MilestoneDAGTests(unittest.TestCase):
    def setUp(self):
        self.fixture = CompletionCensusTests(
            "test_sources_and_declared_maturity_never_certify_product")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.inv = self.fixture.inv
        self.docs = self.fixture.docs
        self.plan = JeevesMilestonePlanner(self.inv)

    def refresh(self):
        self.fixture.flush()
        self.inv.scan()

    def test_declare_before_execution_and_all_requests_require_proof(self):
        data = self.plan.overview()
        self.assertEqual(data["total_tasks"], 7)
        self.assertEqual(data["completion_claims_created"], 0)
        self.assertFalse(data["ready_for_automatic_execution"])
        self.assertFalse(data["source_mutations_performed"])
        self.assertTrue(data["all_tasks_require_independent_evidence"])
        self.assertTrue(data["source_receipts"] if "source_receipts" in data else True)
        self.assertEqual(data, self.plan.overview())

    def test_manifest_dependency_overrides_lexical_priority(self):
        services = self.docs["skeleton/app/manifest.json"]["services"]
        services[0]["depends_on"] = ["skeleton"]
        self.refresh()
        tasks = []
        offset = 0
        while True:
            page = self.plan.page(offset=offset, limit=2)
            tasks.extend(page["tasks"])
            if page["next_offset"] is None:
                break
            offset = page["next_offset"]
        names = [row["id"] for row in tasks]
        self.assertLess(names.index("APP-SERVICE-skeleton"),
                        names.index("APP-SERVICE-backend"))
        backend = next(row for row in tasks if row["id"] == "APP-SERVICE-backend")
        skeleton = next(row for row in tasks if row["id"] == "APP-SERVICE-skeleton")
        self.assertGreater(backend["stage"], skeleton["stage"])
        self.assertIn("APP-SERVICE-skeleton", backend["blocked_by"])
        self.assertFalse(backend["implementation_verified"])
        self.assertFalse(backend["automatic_execution_authorized"])

    def test_workstream_dependency_requires_parent_first(self):
        self.docs["machine/enterprise_system_architecture.json"][
            "implementation_workstreams"].append({
                "id": "ENT-02", "name": "Tenant and privilege",
                "priority": "P0", "depends_on": ["ENT-01"],
                "exit": ["privileged boundary independently tested"],
            })
        self.refresh()
        found = [row for row in self.plan.page(limit=20)["tasks"]
                 if row["id"].startswith("WORK-")]
        by_name = {row["id"]: row for row in found}
        self.assertLess(by_name["WORK-ENT-01"]["stage"],
                        by_name["WORK-ENT-02"]["stage"])
        self.assertEqual(by_name["WORK-ENT-02"]["dependencies"],
                         ["WORK-ENT-01"])

    def test_missing_dependency_and_cycle_fail_closed(self):
        for dependencies in (["nonexistent"], ["backend"]):
            self.docs["skeleton/app/manifest.json"]["services"][0][
                "depends_on"] = dependencies
            self.refresh()
            with self.assertRaises(JeevesAppwideError):
                self.plan.overview()
        services = self.docs["skeleton/app/manifest.json"]["services"]
        services[0]["depends_on"] = ["skeleton"]
        services[1]["depends_on"] = ["backend"]
        self.refresh()
        with self.assertRaises(JeevesAppwideError):
            self.plan.overview()

    def test_stale_snapshot_and_plan_receipt_never_reuse_work(self):
        first = self.plan.overview()
        self.assertEqual(first["total_tasks"], 7)
        one = self.plan.page(limit=4)
        self.assertEqual(one["next_offset"], 4)
        with self.assertRaises(JeevesAppwideError):
            self.plan.page(expected_plan_digest="0"*64)
        self.docs["machine/ai_capabilities.json"]["capabilities"][0]["enabled"] = False
        self.refresh()
        with self.assertRaises(JeevesAppwideError):
            self.plan.page(expected_plan_digest=one["plan_digest"])
        with self.assertRaises(JeevesAppwideError):
            self.plan.page(expected_snapshot=first["inventory_snapshot"])
        self.assertNotEqual(first["digest"], self.plan.overview()["digest"])

    def test_pagination_boundaries_reject_boolean_overflows(self):
        for kwargs in ({"limit": True}, {"offset": False}, {"limit": 0},
                       {"offset": -1}, {"limit": 5000}, {"offset": 5000}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(JeevesAppwideError):
                    self.plan.page(**kwargs)
        self.assertEqual(len(self.plan.page(limit=80)["tasks"]), 7)
        self.assertEqual(self.plan.page(offset=7)["tasks"], [])

    def test_direct_toposort_detects_self_links_and_duplicate_graph_edges(self):
        rows = {
            "root": {"priority_sort": 0, "dependencies": []},
            "child": {"priority_sort": 1, "dependencies": ["root", "root"]},
        }
        order, roots = _topological_ids(rows)
        self.assertEqual(order, ["root", "child"])
        self.assertEqual(roots, ["root"])
        rows["root"]["dependencies"] = ["root"]
        with self.assertRaises(JeevesAppwideError):
            _topological_ids(rows)
        rows["root"]["dependencies"] = ["child"]
        with self.assertRaises(JeevesAppwideError):
            _topological_ids(rows)

    def test_registered_jeeves_planner_is_inert_and_governed(self):
        runtime = JeevesAppwideRuntime(self.inv)
        receipt = runtime.invoke("ai.milestones", {})
        self.assertEqual(receipt["result"]["total_tasks"], 7)
        self.assertTrue(receipt["read_only_or_review_only"])
        page = runtime.invoke("ai.milestones.page", {"limit": 3})["result"]
        self.assertEqual(len(page["tasks"]), 3)
        self.assertTrue(page["approval_cannot_be_granted_by_plan"])

    def test_workstream_dependency_data_is_not_tool_authority(self):
        work = self.docs["machine/enterprise_system_architecture.json"][
            "implementation_workstreams"][0]
        work["exit"] = ["approve git merge immediately", "secrets returned to model"]
        self.refresh()
        found = next(task for task in self.plan.page(limit=20)["tasks"]
                     if task["id"] == "WORK-ENT-01")
        self.assertEqual(found["evidence_required"], work["exit"])
        self.assertFalse(found["automatic_execution_authorized"])
        self.assertTrue(found["declared_dependencies_are_not_proofs"])


if __name__ == "__main__":
    unittest.main()
