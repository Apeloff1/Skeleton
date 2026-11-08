"""2026-11-08 exact-head CI admission, reusable-workflow and safety regressions.

New specialized suites reuse existing bounded PR admissions; release and
destructive cleanup must remain exclusively owner/operator triggered.
"""
from __future__ import annotations

import json
from pathlib import Path
import unittest

from scripts.check_ci_workflow_tiers import (
    MAX_INDEPENDENT_WORKFLOWS, audit, events, independently_triggered,
)

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"
REGISTRY = ROOT / "machine/ci_workflow_tiers.json"
REUSABLE = {
    "reconciliation-exact-head-policy.yml":
        "draft19-gguf-source-qualification.yml",
    "vol249-250-research-reasoning.yml":
        "reconciliation-game-source-qualification.yml",
}
CORE_SOURCE = (
    "draft19-gguf-source-qualification.yml",
    "reconciliation-game-source-qualification.yml",
    "jeeves-atomic-review-regression.yml",
)
PRIVILEGED_MANUAL = (
    "owner-historical-actions-cleanup.yml",
    "release-images.yml",
    "reproducible-release.yml",
)


class StackedSourceWorkflowAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = json.loads(REGISTRY.read_text(encoding="utf-8"))

    def source(self, name):
        return (WORKFLOWS / name).read_text(encoding="utf-8")

    def test_source_automation_stays_inside_finite_registered_capacity(self):
        registered = self.policy["automatic_event_workflows"]
        self.assertEqual(len(registered), MAX_INDEPENDENT_WORKFLOWS)
        self.assertEqual(len(set(registered)), len(registered))
        self.assertEqual(
            set(registered),
            set(self.policy["automatic_event_triggers"]),
        )
        for name in CORE_SOURCE:
            with self.subTest(name=name):
                self.assertIn(name, registered)
                self.assertIn("pull_request", events(self.source(name)))

    def test_privileged_cleanup_and_release_are_not_automatic(self):
        registered = self.policy["automatic_event_workflows"]
        for name in PRIVILEGED_MANUAL:
            with self.subTest(name=name):
                source = self.source(name)
                self.assertNotIn(name, registered)
                self.assertNotIn(name, self.policy["automatic_event_triggers"])
                self.assertEqual(events(source), {"workflow_dispatch"})
                self.assertFalse(independently_triggered(events(source)))

    def test_specialized_suites_use_callable_review_only_qualification(self):
        registered = self.policy["automatic_event_workflows"]
        for name, caller in REUSABLE.items():
            with self.subTest(name=name):
                source = self.source(name)
                self.assertEqual(
                    events(source), {"workflow_call", "workflow_dispatch"}
                )
                self.assertFalse(independently_triggered(events(source)))
                self.assertNotIn(name, registered)
                self.assertIn(
                    "uses: ./.github/workflows/" + name,
                    self.source(caller),
                )
                self.assertIn("  contents: read", source)
                self.assertNotIn("  contents: write", source)
                self.assertNotIn("  packages: write", source)

    def test_automatic_source_qualifiers_pin_real_pull_request_head(self):
        for name in CORE_SOURCE:
            with self.subTest(name=name):
                source = self.source(name)
                self.assertIn("persist-credentials: false", source)
                self.assertIn(
                    "github.event.pull_request.head.sha", source
                )
                self.assertIn("git rev-parse HEAD", source)
                self.assertIn("pull_request", events(source))
                self.assertNotIn("actions/checkout@v", source)

    def test_policy_reusable_checks_only_held_source_not_production(self):
        source = self.source("reconciliation-exact-head-policy.yml")
        self.assertIn("scripts/check_reconciliation_exact_head.py", source)
        self.assertIn("scripts/check_backlog19_actions.py", source)
        self.assertIn("scripts/check_draft19_reconciliation.py", source)
        self.assertNotIn("packages: write", source)
        self.assertNotIn("pull_request:", source)

    def test_research_reusable_called_by_game_source_gate(self):
        game = self.source("reconciliation-game-source-qualification.yml")
        self.assertIn('skeleton/ai/research/**', game)
        self.assertIn('vol249-250-research-reasoning.yml', game)
        self.assertIn("research_reasoning_qualification:", game)

    def test_complete_machine_tier_contract_reports_no_unregistered_auto(self):
        self.assertEqual(
            audit(ROOT), [],
            "Repository machine must not pass with invisible subscribers",
        )


if __name__ == "__main__":
    unittest.main()
