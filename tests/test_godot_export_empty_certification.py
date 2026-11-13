"""Fail-closed certification regressions for exported Godot projects.

These are source-level policy tests, not evidence of native Godot execution.
"""
import unittest

from skeleton.godot_export.report import CertificationReport, merge


class CertificationVerdictTests(unittest.TestCase):
    def test_empty_report_never_certifies(self):
        report = CertificationReport("unexecuted-native-export")
        self.assertFalse(report.ship)
        self.assertEqual(report.exit_code(), 1)
        self.assertFalse(report.to_dict()["ship"])
        self.assertIn("NO-SHIP", report.to_markdown())

    def test_only_nonblocking_case_can_pass_after_execution(self):
        report = CertificationReport("nonblocking-case")
        report.add("GFD-06", True)
        self.assertTrue(report.ship)
        self.assertEqual(report.exit_code(), 0)

    def test_blocking_failure_is_no_ship(self):
        report = CertificationReport("failed-import")
        report.add("GFD-01", False, "Godot executable missing")
        self.assertFalse(report.ship)
        self.assertEqual(report.exit_code(), 1)

    def test_merge_of_unexecuted_reports_is_no_ship(self):
        report = merge("combined", [CertificationReport("import"), CertificationReport("export")])
        self.assertFalse(report.ship)
        self.assertEqual(report.exit_code(), 1)

    def test_merge_preserves_blocking_failure(self):
        first = CertificationReport("import")
        first.add("GFD-01", False)
        second = CertificationReport("export")
        second.add("GFX-05", True)
        self.assertFalse(merge("combined", [first, second]).ship)


if __name__ == "__main__":
    unittest.main()
