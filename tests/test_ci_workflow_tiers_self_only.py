"""Fail-closed CI admission for explicitly owner-dispatched maintenance workflows."""
from pathlib import Path
import unittest

from scripts.check_ci_workflow_tiers import events, independently_triggered


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
MAINTENANCE = (
    "expo54-lockfile-repair.yml",
    "historical-zero-job-canary.yml",
)


class SelfOnlyMaintenanceAdmissionTests(unittest.TestCase):
    def test_owner_maintenance_is_dispatch_only(self):
        for name in MAINTENANCE:
            with self.subTest(name=name):
                source = (WORKFLOWS / name).read_text(encoding="utf-8")
                self.assertEqual(events(source), {"workflow_dispatch"})
                self.assertFalse(independently_triggered(events(source)))
                for new_event in ("pull_request", "schedule", "push", "workflow_run"):
                    modified = source.replace("on:\n", f"on:\n  {new_event}:\n", 1)
                    self.assertIn(new_event, events(modified))
                    self.assertTrue(independently_triggered(events(modified)))

    def test_duplicate_on_block_is_rejected(self):
        for name in MAINTENANCE:
            with self.subTest(name=name):
                source = (WORKFLOWS / name).read_text(encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "exactly one"):
                    events(source + "\non:\n  push:\n")

    def test_historical_canary_retains_owner_and_main_guard(self):
        canary = (WORKFLOWS / MAINTENANCE[1]).read_text(encoding="utf-8")
        self.assertIn("os.environ.get('GH_ACTOR') != 'Apeloff1'", canary)
        self.assertIn("os.environ.get('GH_EVENT') != 'workflow_dispatch'", canary)
        self.assertIn("os.environ.get('GH_REF') != 'refs/heads/main'", canary)


if __name__ == "__main__":
    unittest.main()
