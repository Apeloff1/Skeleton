"""Regression checks for archived specialist workflows and lean active CI."""
from __future__ import annotations

import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.check_ci_workflow_tiers import ROOT, PAUSED_RECOVERY, SCHEDULED_RECOVERY, audit, events


class WorkflowTierTests(unittest.TestCase):
    def test_repo_tiers_are_consistent(self):
        self.assertEqual(audit(ROOT), [])

    def test_masterplan_workflow_references_resolve(self):
        """Signed masterplan evidence paths must continue to name real workflows."""
        masterplan = json.loads(
            (ROOT / "machine/ai_master_plan.json").read_text(encoding="utf-8")
        )
        referenced = set(re.findall(
            r"\.github/workflows/[A-Za-z0-9._-]+\.ya?ml",
            json.dumps(masterplan),
        ))
        self.assertTrue(referenced, "masterplan must retain workflow evidence")
        missing = sorted(
            path for path in referenced if not (ROOT / path).is_file()
        )
        self.assertEqual(missing, [], "masterplan references missing workflows")

    def test_auxiliary_admissions_are_manual_only(self):
        """Keep the 20-trigger cap without dropping required security gates."""
        for name in ("historical-zero-job-canary.yml", "local-ai-boilerplate.yml"):
            source = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
            self.assertEqual(events(source), {"workflow_dispatch"}, name)
        canary = (ROOT / ".github/workflows/historical-zero-job-canary.yml").read_text(encoding="utf-8")
        self.assertIn("os.environ.get('GH_ACTOR') != 'Apeloff1'", canary)
        self.assertIn("os.environ.get('GH_EVENT') != 'workflow_dispatch'", canary)
        readiness = (ROOT / ".github/workflows/merge-readiness.yml").read_text(encoding="utf-8")
        # The full canonical suite now executes in eight exhaustive shards.
        # Verify the admission invokes the real splitter and remains blocked
        # on all shards; do not replace this with a mock or skip-based gate.
        self.assertIn("python scripts/run_domain_suite_shard.py --index", readiness)
        self.assertIn("needs: domain_suite", readiness)
        runner = (ROOT / "scripts/run_domain_suite_shard.py").read_text(encoding="utf-8")
        self.assertIn('options.get("testpaths") != ["skeleton/testing"]', runner)
        self.assertIn('"--tb=short"', runner)
        self.assertIn('"--maxfail=1"', runner)
        self.assertNotIn("--ignore=skeleton/testing/test_local_ai_boilerplate.py", readiness)

    def test_backlog_housekeeping_is_manual_without_weakening_recovery(self):
        """Owner-directed backlog work pauses optional writers, not CI gates."""
        manual = (
            "actions-housekeeping-cli.yml",
            "three-hour-actions-queue-expiry.yml",
            "owner-historical-actions-cleanup.yml",
        )
        for name in manual:
            source = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
            self.assertEqual(events(source), {"workflow_dispatch"}, name)
        queue_drain = (ROOT / ".github/workflows/queue-drain.yml").read_text(encoding="utf-8")
        self.assertIn("schedule", events(queue_drain))
        for name in ("merge-readiness.yml", "backend-quality.yml", "malware-gate.yml",
                     "dependency-review.yml", "secret-scanning.yml",
                     "workflow-input-security.yml"):
            source = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
            self.assertIn("pull_request", events(source), name)

    def test_recovery_registry_preserves_owner_pause_and_ci_gates(self):
        registry = json.loads(
            (ROOT / "machine/ci_workflow_tiers.json").read_text(encoding="utf-8")
        )
        self.assertEqual(set(registry["operational_scheduled_non_pr"]), SCHEDULED_RECOVERY)
        self.assertEqual(set(registry["operational_paused_manual_only"]), PAUSED_RECOVERY)
        self.assertEqual(SCHEDULED_RECOVERY, {"queue-drain.yml"})
        self.assertEqual(len(PAUSED_RECOVERY), 2)
        queue = (ROOT / ".github/workflows/queue-drain.yml").read_text()
        self.assertEqual(events(queue), {"workflow_dispatch", "schedule", "push"})
        for name in PAUSED_RECOVERY:
            with self.subTest(name=name):
                source = (ROOT / ".github/workflows" / name).read_text()
                self.assertEqual(events(source), {"workflow_dispatch"})

    def test_event_parser(self):
        self.assertEqual(events("name: Job\non:\n  workflow_dispatch:\n\njobs:\n"), {"workflow_dispatch"})
        self.assertEqual(events("on:\n  pull_request:\n  push:\njobs:\n"), {"pull_request", "push"})

    def test_specialists_are_archived_and_active_core_remains_required(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / ".github/workflows").mkdir(parents=True)
            (root / ".github/workflows-archive").mkdir()
            (root / "machine").mkdir()
            registry = json.loads((ROOT / "machine/ci_workflow_tiers.json").read_text())
            (root / "machine/ci_workflow_tiers.json").write_text(json.dumps(registry))
            # Include all active YAML workflows so count and core contracts are realistic.
            for source in (ROOT / ".github/workflows").glob("*.yml"):
                (root / ".github/workflows" / source.name).write_text(source.read_text())
            for source in (ROOT / ".github/workflows").glob("*.yaml"):
                (root / ".github/workflows" / source.name).write_text(source.read_text())
            for name in registry["specialized_manual_only"] + registry["required_reusable_workflows"]:
                source = ROOT / ".github/workflows-archive" / name
                (root / ".github/workflows-archive" / name).write_text(source.read_text())
            self.assertEqual(audit(root), [])
            reusable = root / ".github/workflows" / registry["required_reusable_workflows"][0]
            reusable_original = reusable.read_text()
            reusable.write_text(reusable_original.replace("  workflow_call:", "  pull_request:"))
            self.assertTrue(any("required reusable workflow must be callable" in p for p in audit(root)))
            reusable.write_text(reusable_original)
            readiness = root / ".github/workflows/merge-readiness.yml"
            readiness_original = readiness.read_text()
            readiness.write_text(readiness_original.replace(
                "uses: ./.github/workflows/ci.yml", "uses: ./.github/workflows/missing-ci.yml"
            ))
            self.assertTrue(any("required reusable workflow not called" in p for p in audit(root)))
            readiness.write_text(readiness_original)
            evidence = root / ".github/workflows" / "signed-evidence-manual.yml"
            evidence.write_text(
                "name: Signed evidence\n"
                "on:\n"
                "  workflow_dispatch:\n"
                "jobs:\n"
                "  hold:\n"
                "    runs-on: ubuntu-latest\n"
                "    steps:\n"
                "      - run: echo hold\n",
                encoding="utf-8",
            )
            self.assertEqual(audit(root), [])
            evidence.unlink()
            queue = root / ".github/workflows/queue-drain.yml"
            before = queue.read_text()
            queue.write_text(before.replace("  schedule:", "  pull_request:\n  schedule:", 1))
            self.assertTrue(any("operational-only trigger" in x for x in audit(root)))
            queue.write_text(before.replace("permissions: {}", "permissions: write-all", 1))
            self.assertTrue(any("operational-only trigger" in x for x in audit(root)))
            queue.write_text(before)
            paused = root / ".github/workflows/actions-housekeeping-cli.yml"
            before = paused.read_text()
            paused.write_text(before.replace("  workflow_dispatch:",
                                             "  workflow_dispatch:\n  schedule:\n    - cron: '0 * * * *'", 1))
            self.assertTrue(any("paused workflow gained automatic" in x for x in audit(root)))
            paused.write_text(before)
            self.assertEqual(audit(root), [])
            for index in range(10):
                (
                    root / ".github/workflows" / f"automatic-extra-{index}.yml"
                ).write_text(
                    "name: extra\non:\n  pull_request:\njobs:\n  x:\n"
                    "    runs-on: ubuntu-latest\n    steps:\n      - run: true\n",
                    encoding="utf-8",
                )
            self.assertTrue(
                any("unexpected active workflow count" in item for item in audit(root))
            )
            for index in range(10):
                (root / ".github/workflows" / f"automatic-extra-{index}.yml").unlink()
            name = registry["specialized_manual_only"][0]
            spec = root / ".github/workflows-archive" / name
            original = spec.read_text()
            spec.write_text(original.replace("  workflow_dispatch:", "  pull_request:\n  workflow_dispatch:"))
            self.assertTrue(any("archived specialist" in p for p in audit(root)))
            spec.write_text(original)
            (root / ".github/workflows" / name).write_text(original)
            self.assertTrue(any("unexpectedly active" in p for p in audit(root)))
            (root / ".github/workflows" / name).unlink()
            core = root / ".github/workflows" / registry["core_automatic_pr"][0]
            core.write_text("name: disabled\non:\n  workflow_dispatch:\njobs:\n")
            self.assertTrue(any("core PR trigger missing" in p for p in audit(root)))


if __name__ == "__main__":
    unittest.main()
