"""Full-app source-truth census: never confuse declared completion with release."""
from __future__ import annotations

from hashlib import sha1
import json
from pathlib import Path
import tempfile
import unittest

from skeleton.ai.game_builder.jeeves_appwide_fabric import (
    AppwideInventory, JeevesAppwideError, JeevesAppwideRuntime)
from skeleton.ai.game_builder.jeeves_completion_census import (
    JeevesCompletionCensus, SOURCES)


def blob_sha(encoded):
    return sha1(("blob " + str(len(encoded)) + "\0").encode() + encoded).hexdigest()


class CompletionCensusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.master = {
            "thematic_parts": [{"title": "AI Runtime"}, {"title": "Game Production"}],
            "volumes": [
                {"id": 0, "key": "VOL-000", "implementation_status": "verified",
                 "enterprise_grade_state": "designed"},
                {"id": 1, "key": "VOL-001", "implementation_status": "hardened",
                 "enterprise_grade_state": "designed"},
            ]}
        self.docs = {
            "machine/ai_capabilities.json": {
                "capabilities": [
                    {"capability_id": "assistant.text",
                     "implementation_state": "partial",
                     "owner_plane": "application-api", "enabled": True,
                     "required_planes": ["application-api"],
                     "readiness_requirements": ["real model"]},
                    {"capability_id": "assistant.background_agent",
                     "implementation_state": "planned_target",
                     "owner_plane": "orchestration", "enabled": True,
                     "required_planes": ["orchestration"],
                     "readiness_requirements": ["lease"]},
                ]},
            "machine/ai_app_construction.json": {
                "planes": [{"id": "application-api", "owner": "backend"},
                           {"id": "orchestration", "owner": "skeleton/ai"}],
                "gap_register": [{"id": "gap-a", "priority": "P0", "status": "closed"}]},
            "machine/ai_closure_evidence.json": {
                "entries": [{"gap": "gap-a", "gap_status": "closed"}]},
            "machine/ai_master_plan.json": self.master,
            "machine/ai_masterplan_parse_index.json": {
                "sources": {},
                "volume_summary": {"verification_signed": 2}},
            "machine/enterprise_ai_superiority.json": {
                "grade_model": {"states": ["designed", "enterprise_qualified"]}},
            "machine/enterprise_system_architecture.json": {
                "enterprise_domains": [{"id": "ai-execution"}],
                "implementation_workstreams": [{"id": "ENT-01"}],
                "required_journeys": ["prompt to persisted chat"],
                "completion": {"implementation_state": "not_claimed"}},
            "skeleton/app/manifest.json": {
                "services": [
                    {"name": "backend", "role": "application-api", "path": "backend"},
                    {"name": "skeleton", "role": "engine-api", "path": "skeleton"}],
                "required_paths": ["backend/server.py", "skeleton/app/manifest.json"]},
        }
        self.put("backend/server.py", "# backend runtime stub, not proof\n")
        self.put("skeleton/ai/__init__.py", "# canonical AI namespace\n")
        self.flush()
        self.inv = AppwideInventory(self.root)
        self.inv.scan()
        self.census = JeevesCompletionCensus(self.inv)

    def put(self, path, content):
        dest = self.root / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content.encode("utf-8"))

    def flush(self):
        plan_raw = json.dumps(self.docs["machine/ai_master_plan.json"],
                              sort_keys=True).encode()
        self.docs["machine/ai_masterplan_parse_index.json"]["sources"] = {
            "machine/ai_master_plan.json": {"git_blob_sha": blob_sha(plan_raw)}}
        for name, contents in self.docs.items():
            self.put(name, json.dumps(contents, sort_keys=True))
        # Full synthesized manifests are small JSON; always preserve bytes.
        # pyjson default has spaces so the plan blob was intentionally
        # produced with the same canonical options and matches the stored bytes.

    def refresh(self):
        self.inv.scan()

    def test_sources_and_declared_maturity_never_certify_product(self):
        report = self.census.report()
        self.assertTrue(report["read_only"])
        self.assertEqual(report["reconciled_source_files"], len(SOURCES))
        self.assertEqual(report["plan"]["volume_implementation_states"],
                         {"hardened": 1, "verified": 1})
        self.assertEqual(report["plan"]["volume_enterprise_states"], {"designed": 2})
        self.assertTrue(report["plan"]["parse_index_masterplan_git_blob_matches"])
        self.assertEqual(report["plan"]["thematic_domain_count"], 2)
        self.assertIn("ai.completion", [a["id"] for a in report["feature_discovery"]["actions"]])
        self.assertIsNone(report["feature_discovery"]["whole_app_functional_coverage_percent"])
        self.assertEqual(report["ai_product"]["capability_total"], 2)
        self.assertEqual(report["ai_product"]["registry_complete_count"], 0)
        self.assertIsNone(report["ai_product"]["runtime_verified_count"])
        self.assertEqual(report["construction"]["declared_closed_gaps"], 1)
        self.assertEqual(report["application"]["required_paths_present"], 2)
        self.assertFalse(report["readiness"]["release_qualified"])
        self.assertIsNone(report["readiness"]["full_app_completion_percent"])
        self.assertIn("trained_model_quality_not_verified",
                      report["readiness"]["blocking_conditions"])
        self.assertFalse(report["enterprise"]["production_qualified"])
        self.assertEqual(report["authority_defects"], [])

    def test_runtime_action_reuses_admitted_inventory_no_write_authority(self):
        runtime = JeevesAppwideRuntime(self.inv)
        before = (self.root / "backend/server.py").read_bytes()
        receipt = runtime.invoke("ai.completion", {})
        self.assertEqual(receipt["action"], "ai.completion")
        self.assertTrue(receipt["read_only_or_review_only"])
        self.assertEqual(receipt["result"]["reconciled_source_files"], 8)
        self.assertEqual(len(receipt["result"]["source_receipts"]), 8)
        self.assertEqual(before, (self.root / "backend/server.py").read_bytes())

    def test_report_deterministic_and_bound_to_exact_source_hash(self):
        before = self.census.report()
        self.assertEqual(before, self.census.report())
        self.docs["machine/ai_capabilities.json"]["capabilities"][0]["enabled"] = False
        self.flush()
        self.refresh()
        after = self.census.report()
        self.assertNotEqual(before["digest"], after["digest"])
        self.assertNotEqual(
            before["source_receipts"]["machine/ai_capabilities.json"]["sha256"],
            after["source_receipts"]["machine/ai_capabilities.json"]["sha256"])

    def test_stale_signature_reports_failure_without_resigning(self):
        self.docs["machine/ai_masterplan_parse_index.json"]["sources"][
            "machine/ai_master_plan.json"]["git_blob_sha"] = "0" * 40
        self.put("machine/ai_masterplan_parse_index.json",
                 json.dumps(self.docs["machine/ai_masterplan_parse_index.json"],
                            sort_keys=True))
        self.refresh()
        report = self.census.report()
        self.assertFalse(report["plan"]["parse_index_masterplan_git_blob_matches"])
        self.assertIn({"kind": "masterplan_parse_index_source_stale"},
                      report["authority_defects"])
        self.assertIn("inconsistent_or_stale_machine_authority",
                      report["readiness"]["blocking_conditions"])

    def test_authority_gap_mismatch_surfaces_precisely(self):
        self.docs["machine/ai_app_construction.json"]["gap_register"].append(
            {"id": "gap-b", "priority": "P0", "status": "closed"})
        self.flush()
        self.refresh()
        report = self.census.report()
        self.assertIn("construction_closure_ledger_mismatch",
                      [d["kind"] for d in report["authority_defects"]])
        self.assertEqual(report["construction"]["gap_total"], 2)
        self.assertEqual(report["construction"]["closure_ledger_records"], 1)

    def test_p1_gap_is_tracked_but_not_wrongly_required_in_p0_ledger(self):
        self.docs["machine/ai_app_construction.json"]["gap_register"].append(
            {"id": "gap-p1", "priority": "P1", "status": "closed"})
        self.flush()
        self.refresh()
        report = self.census.report()
        self.assertEqual(report["construction"]["gap_total"], 2)
        self.assertEqual(report["construction"]["p0_evidence_gap_total"], 1)
        self.assertEqual(report["construction"]["declared_closed_gaps"], 2)
        self.assertNotIn("construction_closure_ledger_mismatch",
                         [d["kind"] for d in report["authority_defects"]])

    def test_duplicate_capability_identifier_is_fail_closed(self):
        self.docs["machine/ai_capabilities.json"]["capabilities"].append(
            dict(self.docs["machine/ai_capabilities.json"]["capabilities"][0]))
        self.flush()
        self.refresh()
        with self.assertRaises(JeevesAppwideError):
            self.census.report()

    def test_missing_app_paths_block_certification(self):
        self.docs["skeleton/app/manifest.json"]["required_paths"].append(
            "frontend/app/proof.tsx")
        self.flush()
        self.refresh()
        result = self.census.report()
        self.assertIn("frontend/app/proof.tsx",
                      result["application"]["missing_required_paths"])
        self.assertIn("missing_app_required_paths_or_canonical_owners",
                      result["readiness"]["blocking_conditions"])

    def test_no_synthetic_complete_claim_even_when_all_registry_fields_complete(self):
        for cap in self.docs["machine/ai_capabilities.json"]["capabilities"]:
            cap["implementation_state"] = "complete"
        for row in self.docs["machine/ai_master_plan.json"]["volumes"]:
            row["enterprise_grade_state"] = "enterprise_qualified"
        self.flush()
        self.refresh()
        result = self.census.report()
        self.assertEqual(result["ai_product"]["registry_complete_count"], 2)
        self.assertEqual(result["plan"]["enterprise_qualified_volumes"], 2)
        self.assertFalse(result["readiness"]["release_qualified"])
        self.assertIsNone(result["readiness"]["full_app_completion_percent"])

    def test_source_symlink_or_missing_authority_denied(self):
        target = self.root / "machine/ai_capabilities.json"
        target.unlink()
        outside = self.root / "backend/server.py"
        try:
            target.symlink_to(outside)
        except (OSError, NotImplementedError):
            pass
        with self.assertRaises(JeevesAppwideError):
            self.census.report()

    def test_bounded_json_and_no_secrets_leak(self):
        path = "machine/ai_capabilities.json"
        self.put(path, '{"capabilities":[],"capabilities":[]}')
        self.refresh()
        with self.assertRaises(JeevesAppwideError):
            self.census.report()
        self.put(path, "{" + '"padding":"' + ("x" * 1_000_100) + '"}')
        self.refresh()
        with self.assertRaises(JeevesAppwideError):
            self.census.report()

    def test_stale_cursor_rejected(self):
        with self.assertRaises(JeevesAppwideError):
            self.census.report(expected_snapshot="0" * 64)


if __name__ == "__main__":
    unittest.main()
