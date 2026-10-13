"""Release gate policy is separate from current CI execution truth."""
from __future__ import annotations

import json
import unittest

from skeleton.ai.game_builder.jeeves_appwide_fabric import (
    JeevesAppwideError, JeevesAppwideRuntime)
from skeleton.ai.game_builder.jeeves_release_gate_inventory import (
    JeevesReleaseGateInventory)
from tests.test_game_builder_jeeves_completion_census import CompletionCensusTests


class ReleaseGateInventoryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = CompletionCensusTests(
            "test_sources_and_declared_maturity_never_certify_product")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.inv = self.fixture.inv
        self.path = "machine/p1_required_gate_authority.json"
        self.doc = {
            "exact_head_required": True,
            "gates": [{
                "id": "GATE-ONE",
                "workflow_name": "Real required gate",
                "workflow_file": ".github/workflows/real-gate.yml",
                "group": "integration",
                "purpose": "Independent exact-head validation",
                "required_for_terminal_p1_promotion": True,
                "accepted_statuses": ["completed"],
                "accepted_conclusions": ["success"],
            }],
            "groups": [{"name": "integration", "gate_ids": ["GATE-ONE"]}],
            "terminal_policy": {
                "required_gate_count": 1,
                "all_required_gates_must_pass": True,
                "observation_set_must_bind_one_exact_head": True,
                "self_promotion_forbidden": True,
                "authority_digest_must_match": True,
            },
        }
        self.fixture.put(".github/workflows/real-gate.yml",
                         "name: Real required gate\non: workflow_dispatch\n")
        self.refresh()
        self.inventory = JeevesReleaseGateInventory(self.inv)

    def refresh(self):
        self.fixture.put(self.path, json.dumps(self.doc, sort_keys=True))
        self.inv.scan()

    def test_static_presence_never_counts_as_ci_pass(self):
        summary = self.inventory.overview()
        self.assertEqual(summary["required_gates"], 1)
        self.assertEqual(summary["sources_present"], 1)
        self.assertEqual(summary["sources_missing"], 0)
        self.assertEqual(summary["unobserved_exact_head_checks"], 1)
        self.assertEqual(summary["independently_verified_checks"], 0)
        self.assertFalse(summary["release_qualified"])
        self.assertFalse(summary["all_required_checks_pass"])
        self.assertFalse(summary["self_signoff_performed"])
        self.assertTrue(summary["no_ci_queries_or_releases_performed"])
        self.assertEqual(summary, self.inventory.overview())

    def test_absent_workflow_reports_unobserved_not_forged_success(self):
        self.doc["gates"][0]["workflow_file"] = ".github/workflows/missing.yml"
        self.refresh()
        report = self.inventory.overview()
        self.assertEqual(report["sources_missing"], 1)
        page = self.inventory.page(only_missing=True)["gates"]
        self.assertEqual(len(page), 1)
        self.assertEqual(page[0]["runtime_execution_status"], "unobserved")
        self.assertFalse(page[0]["signed_terminal_acceptance"])
        self.assertFalse(page[0]["verified_success"])

    def test_malformed_contract_and_duplicate_ids_fail_closed(self):
        second = dict(self.doc["gates"][0])
        self.doc["gates"].append(second)
        self.doc["terminal_policy"]["required_gate_count"] = 2
        self.doc["groups"][0]["gate_ids"].append("GATE-ONE")
        self.refresh()
        with self.assertRaises(JeevesAppwideError):
            self.inventory.overview()
        self.doc["gates"].pop()
        self.doc["groups"][0]["gate_ids"].pop()
        self.doc["terminal_policy"]["required_gate_count"] = 1
        self.doc["gates"][0]["accepted_conclusions"] = ["success", "skipped"]
        self.refresh()
        with self.assertRaises(JeevesAppwideError):
            self.inventory.overview()

    def test_terminal_policy_cannot_self_promote(self):
        self.doc["terminal_policy"]["self_promotion_forbidden"] = False
        self.refresh()
        with self.assertRaises(JeevesAppwideError):
            self.inventory.overview()
        self.doc["terminal_policy"]["self_promotion_forbidden"] = True
        self.doc["exact_head_required"] = False
        self.refresh()
        with self.assertRaises(JeevesAppwideError):
            self.inventory.overview()

    def test_missing_group_membership_rejected(self):
        self.doc["groups"][0]["gate_ids"] = []
        self.refresh()
        with self.assertRaises(JeevesAppwideError):
            self.inventory.overview()

    def test_untrusted_path_traversal_rejected(self):
        self.doc["gates"][0]["workflow_file"] = ".github/workflows/../../secret.yml"
        self.refresh()
        with self.assertRaises(JeevesAppwideError):
            self.inventory.overview()

    def test_bounded_pagination_and_sha_cursor(self):
        report = self.inventory.overview()
        page = self.inventory.page(limit=1, expected_inventory_digest=report["digest"])
        self.assertEqual(page["next_offset"], None)
        self.assertEqual(len(page["gates"]), 1)
        for kwargs in ({"offset": True}, {"limit": True}, {"limit": 0},
                       {"offset": -1}, {"only_missing": "yes"}, {"limit": 100}):
            with self.subTest(kwargs=kwargs), self.assertRaises(JeevesAppwideError):
                self.inventory.page(**kwargs)
        self.doc["gates"][0]["purpose"] = "Changed independent acceptance"
        self.refresh()
        with self.assertRaises(JeevesAppwideError):
            self.inventory.page(expected_inventory_digest=report["digest"])

    def test_live_registered_jeeves_gate_reader_is_nonexecuting(self):
        runtime = JeevesAppwideRuntime(self.inv)
        summary = runtime.invoke("ai.release.gates", {})["result"]
        self.assertEqual(summary["independently_verified_checks"], 0)
        page = runtime.invoke("ai.release.gates.page", {"limit": 1})["result"]
        self.assertEqual(len(page["gates"]), 1)
        self.assertTrue(page["no_untrusted_ci_result_promotions"])


if __name__ == "__main__":
    unittest.main()
