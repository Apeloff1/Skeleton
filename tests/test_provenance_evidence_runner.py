"""Regression coverage for executable canonical provenance evidence."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import scripts.run_provenance_evidence as evidence


class ProvenanceEvidenceRunnerTests(unittest.TestCase):
    def test_pytest_evidence_runner_rejects_file_with_zero_tests(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            test_file = root / "tests" / "test_inert.py"
            test_file.parent.mkdir(parents=True)
            test_file.write_text("VALUE = 1\n", encoding="utf-8")

            with mock.patch.object(evidence, "REPO_ROOT", root):
                returncode = evidence.run_test(test_file)

        # pytest uses exit status 5 when no tests are collected. The important
        # contract is non-zero: inert evidence must never count as passing.
        self.assertNotEqual(returncode, 0)

    def test_pytest_evidence_runner_executes_real_test(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            test_file = root / "tests" / "test_real.py"
            test_file.parent.mkdir(parents=True)
            test_file.write_text(
                "def test_evidence_executes():\n    assert 2 + 2 == 4\n",
                encoding="utf-8",
            )

            with mock.patch.object(evidence, "REPO_ROOT", root):
                returncode = evidence.run_test(test_file)

        self.assertEqual(returncode, 0)


if __name__ == "__main__":
    unittest.main()
