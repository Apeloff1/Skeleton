"""Regression checks for exact-revision Windows installer archive admission.

These are source-contract checks, not Windows installer execution evidence.
"""
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "windows" / "build_installer.ps1"


class SourceRefPreflightTests(unittest.TestCase):
    def test_archive_checker_is_loaded_from_archived_commit(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('git -C $RepoRoot show "$($SourceCommit):scripts/windows/check_payload_zip.py"', source)
        self.assertIn('$ArchivePreflight = Join-Path $BuildRoot "check_payload_zip.py"', source)
        self.assertNotIn('$ArchivePreflight = Join-Path $RepoRoot "scripts\\windows\\check_payload_zip.py"', source)

    def test_preflight_occurs_before_expansion(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertLess(source.index("& python $ArchivePreflight --archive"), source.index("Expand-Archive -LiteralPath"))
        self.assertLess(source.index("if ($LASTEXITCODE -ne 0 -or -not $ArchivePreflightText)"), source.index("& python $ArchivePreflight --archive"))

    def test_failed_checker_aborts_before_expansion(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('throw "Archived SourceRef has no Windows payload ZIP preflight checker"', source)
        self.assertIn('throw "Windows payload ZIP preflight rejected the archived SourceRef"', source)


if __name__ == "__main__":
    unittest.main()
