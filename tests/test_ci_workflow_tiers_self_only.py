"""Fail-closed CI tier admission tests for pinned maintenance triggers."""
from pathlib import Path
import unittest

from scripts.check_ci_workflow_tiers import self_only_maintenance_trigger


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


class SelfOnlyMaintenanceAdmissionTests(unittest.TestCase):
    def test_only_two_exact_self_change_triggers_are_exempt(self):
        for name in (
            "expo54-lockfile-repair.yml",
            "historical-zero-job-canary.yml",
        ):
            with self.subTest(name=name):
                source = (WORKFLOWS / name).read_text(encoding="utf-8")
                self.assertTrue(self_only_maintenance_trigger(name, source))
                self.assertFalse(
                    self_only_maintenance_trigger("renamed-" + name, source)
                )
                self.assertFalse(
                    self_only_maintenance_trigger(
                        name, source.replace("on:\n", "on:\n  pull_request:\n", 1)
                    )
                )
                self.assertFalse(
                    self_only_maintenance_trigger(
                        name, source.replace("on:\n", "on:\n  schedule:\n", 1)
                    )
                )
                self.assertFalse(
                    self_only_maintenance_trigger(name, source + "\non:\n  push:\n")
                )

    def test_widened_branch_or_path_loses_exemption(self):
        expo = (WORKFLOWS / "expo54-lockfile-repair.yml").read_text(
            encoding="utf-8"
        )
        historical = (WORKFLOWS / "historical-zero-job-canary.yml").read_text(
            encoding="utf-8"
        )
        self.assertFalse(self_only_maintenance_trigger(
            "expo54-lockfile-repair.yml",
            expo.replace("repair/expo54-lockfile-20261027", "main", 1),
        ))
        self.assertFalse(self_only_maintenance_trigger(
            "historical-zero-job-canary.yml",
            historical.replace("paths: ['.github/workflows/historical-zero-job-canary.yml']",
                               "paths: ['**']", 1),
        ))


if __name__ == "__main__":
    unittest.main()
