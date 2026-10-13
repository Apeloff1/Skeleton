"""Exact-source static Jeeves adapter binding check with adversarial gaps."""
from __future__ import annotations

from pathlib import Path
import unittest

from skeleton.ai.game_builder.jeeves_adapter_dispatch_audit import (
    JeevesAdapterDispatchAudit, OWNER, _action_literals)
from skeleton.ai.game_builder.jeeves_appwide_fabric import (
    OPERATIONS, JeevesAppwideError, JeevesAppwideRuntime)
from tests.test_game_builder_jeeves_completion_census import CompletionCensusTests


class AdapterDispatchAuditTests(unittest.TestCase):
    def setUp(self):
        self.fixture = CompletionCensusTests(
            "test_sources_and_declared_maturity_never_certify_product")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        path = Path(__file__).resolve().parent.parent / OWNER
        self.original = path.read_text(encoding="utf-8")
        self.fixture.put(OWNER, self.original)
        self.fixture.inv.scan()
        self.inv = self.fixture.inv
        self.audit = JeevesAdapterDispatchAudit(self.inv)

    def test_all_canonical_reviewed_actions_have_dispatch_syntax(self):
        report = self.audit.overview()
        self.assertEqual(report["registered_actions"], len(OPERATIONS))
        self.assertEqual(report["syntactically_dispatched_actions"],
                         len(OPERATIONS))
        self.assertEqual(report["declared_but_not_dispatched"], [])
        self.assertTrue(report["all_discovered_sources_automatically_callable"] is False)
        self.assertIsNone(report["functional_appwide_coverage_percent"])
        self.assertEqual(report["runtime_effects_executed"], 0)
        self.assertEqual(report, self.audit.overview())
        self.assertGreaterEqual(report["review_gated_actions"], 1)

    def test_external_effects_are_classified_and_never_auto_authorized(self):
        external = {name for name, descriptor in OPERATIONS.items()
                    if descriptor[0] == "external_effect"}
        self.assertEqual(external, {"studio.production.commit_pages",
                                    "studio.production.commit_bundle"})
        self.assertTrue(all(OPERATIONS[name][2] is True for name in external))
        report = self.audit.overview()
        self.assertEqual(report["registered_external_effect"], len(external))
        self.assertEqual(report["runtime_effects_executed"], 0)
        for name in sorted(external):
            with self.subTest(action=name), self.assertRaises(PermissionError):
                JeevesAppwideRuntime(self.inv).invoke(name, {})

    def test_ast_recognizes_grouped_if_without_dynamic_execution(self):
        example = (
            "class JeevesAppwideRuntime:\n"
            "    def invoke(self, action):\n"
            "        if action == 'a':\n"
            "            return 1\n"
            "        elif action in ('b','c'):\n"
            "            return 2\n"
        )
        self.assertEqual(_action_literals(example), {"a", "b", "c"})
        with self.assertRaises(JeevesAppwideError):
            _action_literals("not python - - <")
        with self.assertRaises(JeevesAppwideError):
            _action_literals("class X: pass")

    def test_deleted_dispatch_is_reported_without_changing_registry(self):
        modified = self.original.replace(
            'elif action=="ai.coverage":',
            'elif action=="dropped_static_coverage":', 1
        )
        self.assertNotEqual(modified, self.original)
        self.fixture.put(OWNER, modified)
        self.inv.scan()
        report = self.audit.overview()
        self.assertIn("ai.coverage", report["declared_but_not_dispatched"])
        self.assertFalse(report["source_authority_changed"])
        self.assertEqual(report["runtime_effects_executed"], 0)
        self.assertIn("ai.coverage", [x["action"] for x in self.audit.page(
            only_missing=True)["adapters"]])

    def test_duplicate_or_wrong_owner_class_is_rejected(self):
        bad = ("class JeevesAppwideRuntime:\n"
               "    def invoke(self, action): return 1\n"
               "class JeevesAppwideRuntime:\n"
               "    def invoke(self, action): return 2\n")
        with self.assertRaises(JeevesAppwideError):
            _action_literals(bad)

    def test_optimistic_content_lease_prevents_stale_verdict(self):
        prior = self.audit.overview()
        self.fixture.put(OWNER, self.original + "\n# changed\n")
        self.inv.scan()
        with self.assertRaises(JeevesAppwideError):
            self.audit.page(expected_audit_digest=prior["digest"])
        with self.assertRaises(JeevesAppwideError):
            self.audit.page(expected_snapshot=prior["inventory_snapshot"])
        self.assertNotEqual(prior["source_sha256"],
                            self.audit.overview()["source_sha256"])

    def test_paging_is_bounded_with_no_approval(self):
        first = self.audit.page(limit=1)
        self.assertEqual(len(first["adapters"]), 1)
        self.assertEqual(first["next_offset"], 1)
        for values in ({"limit": True}, {"offset": True}, {"offset": -1},
                       {"limit": 0}, {"limit": 200}, {"only_missing": 1}):
            with self.subTest(values=values), self.assertRaises(JeevesAppwideError):
                self.audit.page(**values)

    def test_can_query_only_through_reviewed_read_action(self):
        runtime = JeevesAppwideRuntime(self.inv)
        summary = runtime.invoke("ai.adapter.audit", {})["result"]
        self.assertEqual(summary["declared_but_not_dispatched"], [])
        page = runtime.invoke("ai.adapter.audit.page", {"limit": 3})["result"]
        self.assertTrue(page["syntax_is_not_functional_execution_proof"])


if __name__ == "__main__":
    unittest.main()
