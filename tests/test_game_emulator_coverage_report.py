"""Read-only operator catalog: candidates must never be confused with a booted core."""

import unittest
from unittest.mock import patch

from scripts.report_game_emulator_coverage import coverage_report


class CoverageReportTests(unittest.TestCase):
    def test_recipe_only_report_does_not_invent_installation(self):
        report = coverage_report()
        rows = report["rows"]
        self.assertGreaterEqual(len(rows), 100)
        self.assertFalse(report["registry_checked"])
        self.assertEqual(report["summary"]["targets"], len(rows))
        self.assertTrue(all(row["approved_core_available"] is None for row in rows))
        self.assertTrue(all(not row["core_boot_verified"] for row in rows))
        self.assertEqual(report["report_sha256"], coverage_report()["report_sha256"])

    def test_approved_core_is_not_hardware_certification(self):
        candidate = coverage_report()["rows"][0]["target_id"]
        from skeleton.jeeves.game_emulator_catalog import canonical_targets
        fake = []
        for name in canonical_targets():
            yes = name == candidate
            fake.append({
                "target_id": name,
                "available": yes,
                "core": {"core_id": "test-approved"} if yes else None,
                "readiness": {"code": "operator_approved_installation" if yes else "not_ready"},
            })
        with patch("scripts.report_game_emulator_coverage.GameEmulatorRegistry") as klass:
            klass.return_value.catalog.return_value = fake
            report = coverage_report("/operator/registry.json")
        chosen = next(row for row in report["rows"] if row["target_id"] == candidate)
        self.assertTrue(chosen["approved_core_available"])
        self.assertEqual(chosen["approved_core_id"], "test-approved")
        self.assertFalse(chosen["hardware_accuracy_verified"])
        self.assertFalse(chosen["controller_verified"])
        self.assertFalse(chosen["training_qualified"])


if __name__ == "__main__":
    unittest.main()
