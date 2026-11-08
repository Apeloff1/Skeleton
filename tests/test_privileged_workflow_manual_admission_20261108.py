"""Regression for privileged workflow admission under the finite workflow ceiling.

Release publication and destructive historical cleanup are opt-in operations.
This does not downgrade the required PR/security workflows or their CI gates.
"""
from __future__ import annotations

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
MANUAL = (
    "release-images.yml",
    "reproducible-release.yml",
    "owner-historical-actions-cleanup.yml",
)


def trigger_events(text: str) -> set[str]:
    """Use the strict production parser; never ignore a malformed event."""
    from scripts.check_ci_workflow_tiers import events
    return events(text)


class ManualPrivilegedWorkflowAdmission(unittest.TestCase):
    def test_release_and_destructive_cleanup_have_no_auto_event(self) -> None:
        for name in MANUAL:
            with self.subTest(name=name):
                source = (WORKFLOWS / name).read_text(encoding="utf-8")
                self.assertEqual(trigger_events(source), {"workflow_dispatch"})

    def test_malformed_or_duplicate_manual_triggers_fail_closed(self) -> None:
        for untrusted in (
            "on:\n  workflow_dispatch:\n  'pull_request':\n",
            "on:\n  workflow_dispatch:\n  workflow_dispatch:\n",
            "on:\n  workflow_dispatch:\n  workflow_dispatch: {}\n",
        ):
            with self.subTest(untrusted=untrusted):
                with self.assertRaises(ValueError):
                    trigger_events(untrusted)

    def test_image_publication_is_opt_in_on_version_tag_with_governance(self) -> None:
        source = (WORKFLOWS / "release-images.yml").read_text(encoding="utf-8")
        self.assertIn("type: boolean", source)
        self.assertIn("default: false", source)
        self.assertIn("inputs.publish == true", source)
        self.assertIn("startsWith(github.ref, 'refs/tags/v')", source)
        self.assertIn("release_governance_verdict.py", source)
        self.assertIn("if: env.PUSH == 'true'", source)
        self.assertIn("if: inputs.publish == true && !startsWith(", source)

    def test_required_pr_security_subscriptions_remain_automatic(self) -> None:
        registry = json.loads((ROOT / "machine" / "ci_workflow_tiers.json").read_text(encoding="utf-8"))
        for name in registry["core_automatic_pr"]:
            with self.subTest(name=name):
                source = (WORKFLOWS / name).read_text(encoding="utf-8")
                self.assertIn("pull_request", trigger_events(source))
        from scripts.check_ci_workflow_tiers import (
            MAX_INDEPENDENT_WORKFLOWS, audit, independently_triggered,
        )

        registered = registry["automatic_event_workflows"]
        self.assertLessEqual(len(registered), MAX_INDEPENDENT_WORKFLOWS)
        self.assertEqual(len(registered), len(set(registered)))
        for name in MANUAL:
            with self.subTest(name=name):
                self.assertNotIn(name, registered)
                self.assertFalse(
                    independently_triggered(
                        trigger_events(
                            (WORKFLOWS / name).read_text(encoding="utf-8")
                        )
                    )
                )
        self.assertEqual(audit(ROOT), [])


if __name__ == "__main__":
    unittest.main()
