"""Proof-based completion measurement. Static files never imply finished AI."""
from __future__ import annotations

from copy import deepcopy
import json
import unittest

from skeleton.ai.game_builder.jeeves_appwide_fabric import (
    JeevesAppwideError, JeevesAppwideRuntime)
from skeleton.ai.game_builder.jeeves_measured_completion import (
    JeevesMeasuredCompletion, STAGES, _percent)
from tests.test_game_builder_jeeves_completion_census import CompletionCensusTests


class MeasuredCompletionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = CompletionCensusTests(
            "test_sources_and_declared_maturity_never_certify_product")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.inv = self.fixture.inv
        self.docs = self.fixture.docs
        self.stages = [
            {"id": name, "source_auto_measure": i == 0,
             "definition": "Measured prerequisite"}
            for i, name in enumerate(STAGES)
        ]
        self.scope = {
            "schema": "skeleton.ai.app_completion_scope.v1",
            "stages": self.stages,
            "evidence_policy": {
                name: True for name in (
                    "source_presence_is_not_functionality",
                    "unknown_must_remain_unknown",
                    "never_infer_ci_from_workflow_file",
                    "never_promote_planned_volume_signatures",
                    "independent_evidence_required",
                    "regression_invalidates_accepted_receipts",
                )
            },
            "families": [
                {
                    "id": f"F{n:02d}", "title": f"Real feature family {n}",
                    "domain": "game" if n % 2 else "ai",
                    "owner": "skeleton/ai",
                    "source_roots": ["backend/server.py"] if n % 2
                        else ["missing/not-created.py"],
                    "acceptance_target": "Independent installed real functionality tested",
                    "required_proof": list(STAGES),
                    "risk_weight": 1,
                }
                for n in range(1, 43)
            ],
        }
        self.gates = {
            "gates": [{
                "id": "GATE-001", "required_for_terminal_p1_promotion": True,
            }]
        }
        self.refresh()
        self.survey = JeevesMeasuredCompletion(self.inv)

    def refresh(self):
        self.fixture.flush()
        self.fixture.put("machine/app_completion_scope.json",
                         json.dumps(self.scope, sort_keys=True))
        self.fixture.put("machine/p1_required_gate_authority.json",
                         json.dumps(self.gates, sort_keys=True))
        self.inv.scan()

    def test_complete_source_does_not_promote_any_independent_stage(self):
        report = self.survey.overview()
        self.assertEqual(report["family_count"], 42)
        self.assertEqual(report["family_static_source_located"], 21)
        self.assertEqual(report["family_static_source_unlocated"], 21)
        self.assertEqual(report["source_presence_percent"], 50.0)
        self.assertEqual(report["owner_root_presence_percent"], 50.0)
        self.assertEqual(report["family_independent_acceptance_stage_obligations"], 168)
        self.assertEqual(report["unknown_independent_acceptance_stages"], 168)
        self.assertEqual(report["independently_passed_acceptance_stages_observed_here"], 0)
        self.assertEqual(report["release_qualified_families_observed_here"], 0)
        self.assertIsNone(report["full_app_completion_percent"])
        self.assertEqual(report["min_proven_release_completion_percent"], 0.0)
        self.assertTrue(report["unknown_or_unqualified_is_not_failed"])
        self.assertTrue(report["measured_source_pct_is_not_functional_completion"])
        self.assertEqual(report, self.survey.overview())

    def test_atomic_canonical_obligations_counted_without_double_scoring(self):
        report = self.survey.overview()
        # 2 volumes, 2 product caps, 2 services, 1 workstream,
        # 1 required enterprise journey, 1 required P1 gate.
        self.assertEqual(report["atomic_product_contract_obligations"], 9)
        atomic = report["atomic_obligation_breakdown"]
        self.assertEqual(atomic["volume_independent_qualification"]["total"], 2)
        self.assertEqual(atomic["product_ai_capabilities"]["total"], 2)
        self.assertEqual(atomic["application_services"]["total"], 2)
        self.assertEqual(atomic["enterprise_workstreams"]["total"], 1)
        self.assertEqual(atomic["enterprise_journeys"]["total"], 1)
        self.assertEqual(atomic["mandatory_release_gates"]["total"], 1)
        self.assertIsNone(
            atomic["mandatory_release_gates"]["current_head_successfully_observed"])
        self.assertIsNone(
            atomic["application_services"]["independently_running"])
        self.assertEqual(
            atomic["product_ai_capabilities"]["registry_complete"], 0)

    def test_paged_family_status_does_not_claim_working_feature(self):
        report = self.survey.overview()
        page = self.survey.page(offset=0, limit=2,
                                expected_measurement_digest=report["digest"])
        self.assertEqual(page["total_matches"], 42)
        self.assertEqual(page["next_offset"], 2)
        self.assertEqual(len(page["families"]), 2)
        self.assertEqual(page["families"][0]["id"], "F01")
        self.assertTrue(page["families"][0]["source_discovered"])
        self.assertFalse(page["families"][0]["release_qualified"])
        self.assertEqual(page["families"][0]["stage_status"]["source_owner"],
                         "located")
        self.assertEqual(page["families"][0]["stage_status"]["user_journey"],
                         "unverified")
        self.assertTrue(page["missing_acceptance_receipts_never_count_as_passes"])
        self.assertEqual(self.survey.page(only_missing=True)["total_matches"], 21)
        self.assertEqual(self.survey.page(domain="game")["total_matches"], 21)
        self.assertEqual(self.survey.page(domain="ai")["total_matches"], 21)

    def test_missing_required_source_not_implicitly_failed_feature(self):
        unknown = self.survey.page(only_missing=True)["families"][0]
        self.assertFalse(unknown["source_discovered"])
        self.assertEqual(unknown["stage_status"]["source_owner"],
                         "not_located")
        self.assertTrue(unknown["source_coverage_is_only_static"])
        self.assertEqual(unknown["independent_stages_unknown"], 4)
        self.assertFalse(unknown["eligible_for_automatic_signoff"])

    def test_registry_complete_label_still_not_release(self):
        for capability in self.docs["machine/ai_capabilities.json"]["capabilities"]:
            capability["implementation_state"] = "complete"
        for volume in self.docs["machine/ai_master_plan.json"]["volumes"]:
            volume["enterprise_grade_state"] = "enterprise_qualified"
        self.refresh()
        result = self.survey.overview()
        self.assertEqual(result["atomic_obligation_breakdown"][
            "product_ai_capabilities"]["registry_complete"], 2)
        self.assertEqual(result["atomic_obligation_breakdown"][
            "volume_independent_qualification"]["registry_enterprise_qualified"], 2)
        self.assertIsNone(result["full_app_completion_percent"])
        self.assertEqual(result["release_qualified_families_observed_here"], 0)
        self.assertEqual(result["unknown_independent_acceptance_stages"], 168)

    def test_stale_scope_sha_and_same_length_source_change_are_rejected(self):
        before = self.survey.overview()
        self.scope["families"][0]["title"] = "Real feature familx 1"
        self.refresh()
        after = self.survey.overview()
        self.assertNotEqual(before["scope_sha256"], after["scope_sha256"])
        self.assertNotEqual(before["digest"], after["digest"])
        with self.assertRaises(JeevesAppwideError):
            self.survey.overview(expected_scope_sha256=before["scope_sha256"])
        with self.assertRaises(JeevesAppwideError):
            self.survey.page(expected_measurement_digest=before["digest"])

    def test_denom_cannot_shrink_to_inflate_static_coverage(self):
        self.scope["families"] = self.scope["families"][:1]
        self.refresh()
        with self.assertRaises(JeevesAppwideError):
            self.survey.overview()
        # Rebuild in a new fixture on subsequent tests: this instance stays fail-closed.

    def test_duplicate_family_private_root_and_automatic_runtime_proof_rejected(self):
        self.scope["families"][1]["id"] = "F01"
        self.refresh()
        with self.assertRaises(JeevesAppwideError):
            self.survey.overview()
        self.scope["families"][1]["id"] = "F02"
        self.scope["families"][0]["source_roots"] = [".env"]
        self.refresh()
        with self.assertRaises(JeevesAppwideError):
            self.survey.overview()
        self.scope["families"][0]["source_roots"] = ["backend/server.py"]
        self.scope["stages"][2]["source_auto_measure"] = True
        self.refresh()
        with self.assertRaises(JeevesAppwideError):
            self.survey.overview()

    def test_policy_removal_and_untrusted_gate_downgrade_fail_closed(self):
        self.scope["evidence_policy"]["independent_evidence_required"] = False
        self.refresh()
        with self.assertRaises(JeevesAppwideError):
            self.survey.overview()
        self.scope["evidence_policy"]["independent_evidence_required"] = True
        self.gates["gates"][0]["required_for_terminal_p1_promotion"] = False
        self.refresh()
        with self.assertRaises(JeevesAppwideError):
            self.survey.overview()

    def test_paging_boolean_tricks_and_invalid_filters_rejected(self):
        for params in (
            {"limit": True}, {"offset": False}, {"offset": -1},
            {"limit": 0}, {"limit": 999}, {"only_missing": "yes"},
            {"domain": True}, {"domain": "other"},
        ):
            with self.subTest(params=params):
                with self.assertRaises(JeevesAppwideError):
                    self.survey.page(**params)

    def test_single_missing_or_oversized_canonical_scope_fails_closed(self):
        self.fixture.put("machine/app_completion_scope.json",
                         '{"families":[],"families":[]}')
        self.inv.scan()
        with self.assertRaises(JeevesAppwideError):
            self.survey.overview()
        self.fixture.put("machine/app_completion_scope.json",
                         '{"pad":"' + "a" * 130000 + '"}')
        self.inv.scan()
        with self.assertRaises(JeevesAppwideError):
            self.survey.overview()

    def test_existing_appwide_read_action_is_approved_read_only(self):
        jeeves = JeevesAppwideRuntime(self.inv)
        receipt = jeeves.invoke("ai.product.measure", {})
        self.assertTrue(receipt["read_only_or_review_only"])
        self.assertEqual(receipt["result"]["family_count"], 42)
        self.assertIsNone(receipt["result"]["full_app_completion_percent"])
        family = jeeves.invoke("ai.product.measure.page", {"limit": 1})["result"]
        self.assertEqual(len(family["families"]), 1)
        self.assertTrue(family["product_release_not_claimed"])

    def test_real_loopback_studio_measurement_route_is_authenticated_and_inert(self):
        import http.client
        import threading
        from pathlib import Path
        from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
        from skeleton.ai.game_builder.game_workspace_server import create_workspace_server

        root = self.fixture.root
        ws = GameWorkspace.create(str(root / "studio_workspace"), authorized=True)
        ws.create_project("measurement", "rpg", authorized=True)
        server = create_workspace_server(ws, port=0, repo_root=root)
        runner = threading.Thread(target=server.serve_forever, daemon=True)
        runner.start()
        try:
            def request(method, endpoint, data=None, authorized=True):
                connection = http.client.HTTPConnection(
                    "127.0.0.1", server.server_port, timeout=8)
                headers = {"Host": f"127.0.0.1:{server.server_port}"}
                if authorized:
                    headers["X-Game-Studio-Token"] = server.secret
                if data is not None:
                    headers["Content-Type"] = "application/json"
                connection.request(
                    method, endpoint,
                    body=json.dumps(data) if data is not None else None,
                    headers=headers,
                )
                response = connection.getresponse()
                result = response.status, json.loads(response.read())
                connection.close()
                return result

            self.assertEqual(
                request("POST", "/api/jeeves-appwide-invoke", {
                    "action": "ai.product.measure", "params": {}},
                    authorized=False)[0], 403)
            status, report = request("POST", "/api/jeeves-appwide-invoke", {
                "action": "ai.product.measure", "params": {}})
            self.assertEqual(status, 200)
            self.assertEqual(report["result"]["family_count"], 42)
            self.assertIsNone(report["result"]["full_app_completion_percent"])
            self.assertEqual(report["result"]["atomic_product_contract_obligations"], 9)
            digest = report["result"]["digest"]
            status, page = request("POST", "/api/jeeves-appwide-invoke", {
                "action": "ai.product.measure.page",
                "params": {"limit": 2, "expected_measurement_digest": digest},
            })
            self.assertEqual(status, 200)
            self.assertEqual(len(page["result"]["families"]), 2)
            self.assertTrue(page["result"]["product_release_not_claimed"])
            self.assertEqual(request("POST", "/api/jeeves-appwide-invoke", {
                "action": "ai.product.measure.page",
                "params": {"expected_measurement_digest": "0" * 64}})[0], 400)
            self.assertFalse((root / "source_mutated.txt").exists())
        finally:
            server.shutdown()
            server.server_close()
            runner.join(timeout=2)

    def test_finite_exact_percent_never_overflows(self):
        self.assertEqual(_percent(0, 42), 0.0)
        self.assertEqual(_percent(1, 42), 2.38)
        self.assertEqual(_percent(42, 42), 100.0)
        for n,d in ((43,42),(-1,42),(1,0),(True,42),(1,True)):
            with self.assertRaises(JeevesAppwideError):
                _percent(n,d)


if __name__ == "__main__":
    unittest.main()
