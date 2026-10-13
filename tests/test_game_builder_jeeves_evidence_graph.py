"""Adversarial truth and scale tests for Jeeves canonical evidence graph."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

from skeleton.ai.game_builder.jeeves_appwide_fabric import (
    AppwideInventory, JeevesAppwideError, JeevesAppwideRuntime)
from skeleton.ai.game_builder.jeeves_evidence_graph import (
    JeevesEvidenceGraph, _safe_path)
from tests.test_game_builder_jeeves_completion_census import CompletionCensusTests


class EvidenceGraphTests(unittest.TestCase):
    def setUp(self):
        # Reuse the synthetic eight-authority sandbox rather than rely on
        # installed models, network data, CI accounts or mutable mainline.
        self.fixture = CompletionCensusTests(
            "test_sources_and_declared_maturity_never_certify_product")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.docs = self.fixture.docs
        self.inv = self.fixture.inv
        self.graph = JeevesEvidenceGraph(self.inv)

    def refresh(self):
        self.fixture.flush()
        self.inv.scan()

    def test_schema_and_product_scopes_are_declared_not_executable(self):
        report = self.graph.overview()
        kinds = report["kind_counts"]
        self.assertEqual(kinds["masterplan_volume"], 2)
        self.assertEqual(kinds["ai_product_capability"], 2)
        self.assertEqual(kinds["architecture_plane"], 2)
        self.assertEqual(kinds["construction_gap"], 1)
        self.assertEqual(kinds["application_service"], 2)
        self.assertEqual(kinds["enterprise_domain"], 1)
        self.assertEqual(kinds["enterprise_workstream"], 1)
        self.assertEqual(kinds["required_end_to_end_journey"], 1)
        self.assertTrue(report["declarations_are_not_permissions"])
        self.assertTrue(report["source_presence_is_not_a_running_app"])
        self.assertEqual(report, self.graph.overview())
        self.assertEqual(report["inventory_snapshot"], self.inv._digest)
        self.assertEqual(len(report["source_receipts"]), 6)

    def test_capability_ownership_and_dependencies_are_typed(self):
        report = self.graph.neighborhood("cap:assistant.text", depth=1)
        found = {node["id"] for node in report["nodes"]}
        self.assertIn("cap:assistant.text", found)
        self.assertIn("plane:application-api", found)
        relations = {edge["relation"] for edge in report["edges"]}
        self.assertEqual(relations, {"owned_by_plane", "requires_plane"})
        self.assertTrue(all(edge["runtime_verified"] is False
                            for edge in report["edges"]))
        self.assertTrue(report["query_does_not_confer_execution_authority"])
        self.assertFalse(report["runtime_verification_performed"])

    def test_enterprise_workstreams_expose_dependencies_not_proof(self):
        self.docs["machine/enterprise_system_architecture.json"][
            "implementation_workstreams"].append({
                "id": "ENT-02", "priority": "P0",
                "name": "Least-privilege service credentials",
                "depends_on": ["ENT-01"],
                "exit": ["specific cross-service adversarial tests"],
            })
        self.refresh()
        result = self.graph.neighborhood("work:ENT-02", direction="outgoing")
        self.assertEqual([edge["relation"] for edge in result["edges"]],
                         ["depends_on"])
        self.assertEqual(result["edges"][0]["to"], "work:ENT-01")
        self.assertTrue(result["query_does_not_confer_execution_authority"])

    def test_journey_to_volumes_requires_independent_qualification(self):
        self.docs["machine/enterprise_ai_superiority.json"][
            "end_to_end_qualification"] = {"golden_journeys": [{
                "id": "ENT-E2E-01",
                "name": "Evidence-backed answer with 2 sources",
                "volume_refs": ["VOL-000", "VOL-001"]}]}
        self.refresh()
        report = self.graph.neighborhood("ai_journey:ENT-E2E-01",
                                          direction="outgoing", depth=1)
        self.assertEqual({row["to"] for row in report["edges"]},
                         {"vol:VOL-000", "vol:VOL-001"})
        self.assertEqual({n["maturity"] for n in report["nodes"]
                          if n["kind"] == "masterplan_volume"},
                         {"designed"} if False else {"verified", "hardened"})
        self.assertFalse(self.fixture.census.report()["readiness"]["release_qualified"])

    def test_volume_source_links_and_untrusted_source_names(self):
        self.docs["machine/ai_master_plan.json"]["volumes"][0][
            "implementation_paths"] = [
                "backend/server.py", "machine/unavailable.py",
                "machine/.env", "backend/../secret.txt",
            ]
        self.docs["machine/ai_master_plan.json"]["volumes"][0][
            "tests"] = ["backend/server.py"]
        self.refresh()
        result = self.graph.neighborhood("vol:VOL-000", depth=1,
                                          direction="outgoing")
        targets = {x["to"] for x in result["edges"]}
        self.assertEqual(targets, {"path:backend/server.py"})
        self.assertGreater(
            self.graph.overview()["skipped_or_unverified"][
                "unavailable_or_restricted_path"], 0)
        self.assertNotIn("machine/.env", json.dumps(result))

    def test_reverse_impact_identifies_volume_and_qualification_journey(self):
        self.docs["machine/ai_master_plan.json"]["volumes"][0][
            "implementation_paths"] = ["backend/server.py"]
        self.docs["machine/ai_master_plan.json"]["volumes"][1][
            "tests"] = ["backend/server.py"]
        self.docs["machine/enterprise_ai_superiority.json"][
            "end_to_end_qualification"] = {
                "golden_journeys": [{
                    "id": "ENT-E2E-01", "name": "Source-linked acceptance",
                    "volume_refs": ["VOL-000"]}]}
        self.refresh()
        graph_digest = self.graph.overview()["digest"]
        impact = self.graph.impact(["backend/server.py"],
                                   expected_graph_digest=graph_digest)
        self.assertEqual(impact["targeted_paths"], 1)
        self.assertEqual({n["id"] for n in impact["sources"][0]["dependent_nodes"]},
                         {"vol:VOL-000", "vol:VOL-001", "ai_journey:ENT-E2E-01"})
        self.assertTrue(impact["whole_repo_dependency_graph_not_claimed"])
        self.assertTrue(impact["no_changes_or_tests_run"])
        self.assertTrue(impact["sources"][0]["source_content_not_loaded"])
        self.assertEqual(self.graph.impact(["backend/server.py"]), impact)
        limited = self.graph.impact(["backend/server.py"], max_results=1)
        self.assertTrue(limited["sources"][0]["truncated"])
        self.assertEqual(limited["sources"][0]["dependent_count"], 3)

    def test_reverse_impact_private_unknown_or_stale_refs_fail_closed(self):
        with self.assertRaises(JeevesAppwideError):
            self.graph.impact([".env"])
        with self.assertRaises(JeevesAppwideError):
            self.graph.impact(["backend/../server.py"])
        with self.assertRaises(JeevesAppwideError):
            self.graph.impact(["backend/server.py", "backend/server.py"])
        with self.assertRaises(JeevesAppwideError):
            self.graph.impact([True])
        with self.assertRaises(JeevesAppwideError):
            self.graph.impact(["backend/server.py"], max_results=True)
        with self.assertRaises(JeevesAppwideError):
            self.graph.impact(["backend/server.py"],
                              expected_graph_digest="0" * 64)

    def test_readable_directory_is_not_an_executable_adapter(self):
        self.assertEqual(
            _safe_path("backend", self.inv, {"backend"}), "backend")
        self.assertIsNone(_safe_path("backend/../../etc", self.inv, {"backend"}))
        self.assertIsNone(_safe_path("private.pem", self.inv, {"private.pem"}))
        self.assertIsNone(_safe_path("/etc/passwd", self.inv, set()))

    def test_selected_graph_cursor_explicitly_rejects_stale_source_hash(self):
        old = self.graph.overview()
        self.assertEqual(
            old["digest"],
            self.graph.neighborhood("cap:assistant.text")["graph_digest"])
        self.docs["machine/ai_capabilities.json"]["capabilities"][0][
            "enabled"] = False
        self.refresh()
        new = self.graph.overview()
        self.assertNotEqual(old["digest"], new["digest"])
        with self.assertRaises(JeevesAppwideError):
            self.graph.neighborhood(
                "cap:assistant.text", expected_graph_digest=old["digest"])

    def test_no_negative_boolean_unbounded_or_nonexistent_nodes(self):
        with self.assertRaises(JeevesAppwideError):
            self.graph.neighborhood("cap:assistant.text", limit=0)
        with self.assertRaises(JeevesAppwideError):
            self.graph.neighborhood("cap:assistant.text", depth=True)
        with self.assertRaises(JeevesAppwideError):
            self.graph.neighborhood("cap:assistant.text", depth=4)
        with self.assertRaises(JeevesAppwideError):
            self.graph.neighborhood("cap:assistant.text", limit=100_000)
        with self.assertRaises(JeevesAppwideError):
            self.graph.neighborhood("cap:nonexistent")
        with self.assertRaises(JeevesAppwideError):
            self.graph.neighborhood("cap:assistant.text", direction="write")

    def test_graph_rejects_missing_or_corrupted_mandatory_authority(self):
        self.fixture.put("machine/ai_app_construction.json", '{"planes":true}')
        self.inv.scan()
        with self.assertRaises((JeevesAppwideError, TypeError, KeyError)):
            self.graph.overview()
        self.fixture.put("machine/ai_app_construction.json",
                         '{"planes":[],"planes":[]}')
        self.inv.scan()
        with self.assertRaises(JeevesAppwideError):
            self.graph.overview()

    def test_requested_depth_is_bounded_and_not_fake_full_reachability(self):
        root = self.graph.neighborhood("cap:assistant.text", depth=0)
        self.assertEqual(len(root["nodes"]), 1)
        self.assertEqual(root["edges"], [])
        page = self.graph.neighborhood("cap:assistant.text", depth=3, limit=1)
        self.assertEqual(len(page["nodes"]), 1)
        self.assertEqual(page["edges"], [])
        self.assertEqual(page["node_limit"], 1)

    def test_large_bounded_graph_survives_thousands_of_volume_edges(self):
        prototype = self.docs["machine/ai_master_plan.json"]["volumes"][0]
        expanded = [deepcopy(prototype) for _ in range(400)]
        for i, row in enumerate(expanded):
            row.update(key="VOL-%03d" % i, id=i)
            row["implementation_paths"] = ["backend/server.py"] * 25
            row["tests"] = ["backend/server.py"] * 25
        self.docs["machine/ai_master_plan.json"]["volumes"] = expanded
        self.refresh()
        stats = self.graph.overview()
        self.assertEqual(stats["kind_counts"]["masterplan_volume"], 400)
        self.assertEqual(stats["relation_counts"]["declares_implementation_at"],
                         400)
        self.assertEqual(stats["relation_counts"]["declares_test_at"], 400)
        self.assertLess(stats["node_count"], 1500)
        self.assertFalse(stats["source_presence_is_not_a_running_app"] is False)

    def test_same_length_content_change_invalidates_graph_source_receipt(self):
        original = self.graph.overview()
        self.docs["machine/ai_capabilities.json"]["capabilities"][0][
            "enabled"] = False
        self.refresh()
        after = self.graph.overview()
        self.assertNotEqual(original["source_receipts"][
            "machine/ai_capabilities.json"],
            after["source_receipts"]["machine/ai_capabilities.json"])


if __name__ == "__main__":
    unittest.main()
