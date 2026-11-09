"""Focused regressions for archived satellite integrity auditing."""
import unittest

from scripts.audit_satellite_integrity import (
    STALE_UI,
    STUB,
    TRUNC,
    normalized,
    path_problem,
)


class SatelliteIntegrityTests(unittest.TestCase):
    def test_lowercase_import_is_portable(self):
        self.assertIsNone(STALE_UI.search("import Toast from '../components/ui/Toast';"))

    def test_old_cased_import_is_detected(self):
        for target in (
            "../components/UI/Toast",
            "./UI/LoadingScreen",
            "@/components/UI/ErrorBanner",
        ):
            with self.subTest(target=target):
                self.assertIsNotNone(STALE_UI.search(target))

    def test_portable_short_filename(self):
        self.assertEqual(path_problem("satellites/branch-snapshots/a/frontend/components/ui/Toast.tsx"), [])

    def test_windows_reserved_and_long_filename(self):
        self.assertIn("Windows-invalid component", path_problem("satellites/NUL.tsx"))
        self.assertIn("path exceeds 190 units", path_problem("satellites/" + "x" * 184 + ".tsx"))

    def test_unicode_case_equivalence(self):
        self.assertEqual(normalized("CAFÉ"), normalized("cafe\u0301"))

    def test_stub_is_only_a_review_marker(self):
        self.assertIsNotNone(STUB.search("raise NotImplementedError()"))
        self.assertIsNotNone(STUB.search("throw new Error('not implemented');"))
        self.assertIsNone(STUB.search("return implementedValue;"))

    def test_explicit_truncation_marker(self):
        self.assertIsNotNone(TRUNC.search("[truncated]"))
        self.assertIsNone(TRUNC.search("truncate_history(max_entries=100)"))


if __name__ == "__main__":
    unittest.main()
