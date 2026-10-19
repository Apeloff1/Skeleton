"""Regression checks for archived specialist workflows and lean active CI."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.check_ci_workflow_tiers import ROOT, audit, events


class WorkflowTierTests(unittest.TestCase):
    def test_repo_tiers_are_consistent(self):
        self.assertEqual(audit(ROOT), [])

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
