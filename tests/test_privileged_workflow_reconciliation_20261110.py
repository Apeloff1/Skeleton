"""Proof that release publication and historical cleanup stay separately authorized.

A version tag may trigger release verification; publication still requires
protected exact-head governance. Owner cleanup never subscribes to a tag,
pull request, ordinary push, or a schedule.
"""
from __future__ import annotations

import json
from pathlib import Path
import unittest

from scripts.check_ci_workflow_tiers import (
    ROOT, PAUSED_RECOVERY, SCHEDULED_RECOVERY, audit, events,
)


class PrivilegedWorkflowCustodyTests(unittest.TestCase):
    def setUp(self):
        self.workflows = ROOT / ".github" / "workflows"

    def source(self, filename):
        return (self.workflows / filename).read_text(encoding="utf-8")

    def test_owner_cleanup_and_paused_writers_require_explicit_dispatch(self):
        for filename in ("owner-historical-actions-cleanup.yml", *sorted(PAUSED_RECOVERY)):
            with self.subTest(filename=filename):
                source = self.source(filename)
                self.assertEqual(events(source), {"workflow_dispatch"})
                self.assertNotIn("  pull_request:", source)
                self.assertNotIn("  schedule:", source)
                self.assertNotIn("  push:", source)

    def test_release_tag_subscriptions_never_bypass_governance(self):
        for filename in ("release-images.yml", "reproducible-release.yml"):
            with self.subTest(filename=filename):
                source = self.source(filename)
                self.assertEqual(events(source), {"push", "workflow_dispatch"})
                self.assertIn('tags: ["v*"]', source)
                self.assertIn("release_governance_verdict.py", source)
                self.assertIn("github.token", source)
                self.assertNotIn("  pull_request:", source)
                self.assertNotIn("  workflow_run:", source)
        image = self.source("release-images.yml")
        self.assertIn("PUSH: ${{ github.event_name == 'push'", image)
        self.assertIn("if: env.PUSH == 'true'", image)
        self.assertIn("--sha", image)

    def test_only_queue_drain_is_automatic_operational_recovery(self):
        policy = json.loads((ROOT / "machine/ci_workflow_tiers.json").read_text(encoding="utf-8"))
        self.assertEqual(set(policy["operational_scheduled_non_pr"]), SCHEDULED_RECOVERY)
        self.assertEqual(set(policy["operational_paused_manual_only"]), PAUSED_RECOVERY)
        self.assertEqual(SCHEDULED_RECOVERY, {"queue-drain.yml"})
        self.assertEqual(audit(ROOT), [])


if __name__ == "__main__":
    unittest.main()
