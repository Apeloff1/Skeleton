"""Fast/specialized tier audit remains fail-closed without running GitHub."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.check_ci_workflow_tiers import ROOT, audit, events


class WorkflowTierTests(unittest.TestCase):
    def test_repo_tiers_are_consistent(self):
        self.assertEqual(audit(ROOT), [])

    def test_trigger_event_parser(self):
        self.assertEqual(events("name: Job\non:\n  workflow_dispatch:\n\njobs:\n  x:\n"), {"workflow_dispatch"})
        self.assertEqual(events("on:\n  pull_request:\n    branches: [main]\n  push:\n    branches: [main]\njobs:\n"), {"pull_request", "push"})

    def test_auto_activating_specialist_fails_and_core_disabling_fails(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / ".github/workflows").mkdir(parents=True)
            (root / "machine").mkdir()
            registry = json.loads((ROOT / "machine/ci_workflow_tiers.json").read_text())
            (root / "machine/ci_workflow_tiers.json").write_text(json.dumps(registry))
            for file in registry["specialized_manual_only"] + registry["core_automatic_pr"]:
                body = (ROOT / ".github/workflows" / file).read_text()
                (root / ".github/workflows" / file).write_text(body)
            self.assertEqual(audit(root), [])
            spec = root / ".github/workflows" / registry["specialized_manual_only"][0]
            spec.write_text(spec.read_text().replace("  workflow_dispatch:", "  pull_request:\n  workflow_dispatch:"))
            self.assertTrue(any("dispatch-only" in x for x in audit(root)))
            spec.write_text((ROOT / ".github/workflows" / registry["specialized_manual_only"][0]).read_text())
            core = root / ".github/workflows" / registry["core_automatic_pr"][0]
            core.write_text("name: disabled\non:\n  workflow_dispatch:\njobs:\n")
            self.assertTrue(any("core required/security" in x for x in audit(root)))


if __name__ == "__main__":
    unittest.main()
