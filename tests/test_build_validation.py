from __future__ import annotations

import unittest

from skeleton.automation.build_contracts import (
    ArchitecturePlan,
    BuildBudget,
    CandidateFile,
    FileIntent,
)
from skeleton.automation.build_validation import (
    BuildValidationError,
    compact_diagnostics,
    validate_candidate,
    validate_file,
)


def architecture(
    *paths: str,
) -> ArchitecturePlan:
    return ArchitecturePlan(
        objective="bounded feature",
        rationale="test validation",
        files=tuple(
            FileIntent(
                path=path,
                purpose="test",
                operation="create",
            )
            for path in paths
        ),
        test_intents=("validate",),
        acceptance=("publishable",),
        risks=(),
        assumptions=(),
    )


class FileValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.budget = BuildBudget()

    def test_valid_python_is_publishable(self) -> None:
        report = validate_file(
            CandidateFile(
                path="skeleton/example.py",
                content="def answer() -> int:\n    return 42\n",
            ),
            budget=self.budget,
        )
        self.assertFalse(report.blocking)

    def test_invalid_python_blocks(self) -> None:
        report = validate_file(
            CandidateFile(
                path="skeleton/example.py",
                content="def broken(:\n",
            ),
            budget=self.budget,
        )
        self.assertTrue(report.blocking)
        self.assertTrue(
            any(
                item.code == "python-syntax"
                for item in report.diagnostics
            )
        )

    def test_duplicate_json_key_blocks(self) -> None:
        report = validate_file(
            CandidateFile(
                path="docs/example.json",
                content='{"a":1,"a":2}\n',
            ),
            budget=self.budget,
        )
        self.assertTrue(report.blocking)
        self.assertTrue(
            any(
                item.code == "json-parse"
                for item in report.diagnostics
            )
        )

    def test_invalid_toml_blocks(self) -> None:
        report = validate_file(
            CandidateFile(
                path="docs/example.toml",
                content='name = "unterminated\n',
            ),
            budget=self.budget,
        )
        self.assertTrue(report.blocking)
        self.assertTrue(
            any(
                item.code == "toml-parse"
                for item in report.diagnostics
            )
        )

    def test_conflict_marker_blocks(self) -> None:
        report = validate_file(
            CandidateFile(
                path="docs/example.md",
                content=(
                    "<<<<<<< ours\n"
                    "a\n"
                    "=======\n"
                    "b\n"
                    ">>>>>>> theirs\n"
                ),
            ),
            budget=self.budget,
        )
        codes = {item.code for item in report.diagnostics}
        self.assertIn("merge-conflict-marker", codes)
        self.assertTrue(report.blocking)

    def test_private_key_marker_blocks(self) -> None:
        report = validate_file(
            CandidateFile(
                path="docs/example.md",
                content=(
                    ("-----BEGIN " + "PRIVATE KEY-----\n")
                    + "fake-but-forbidden\n"
                    + "-----END PRIVATE KEY-----\n"
                ),
            ),
            budget=self.budget,
        )
        self.assertTrue(
            any(
                item.code == "secret-private-key"
                for item in report.diagnostics
            )
        )

    def test_github_pat_marker_blocks(self) -> None:
        report = validate_file(
            CandidateFile(
                path="docs/example.md",
                content=(
                    "token github_pat_"
                    + ("a" * 30)
                    + "\n"
                ),
            ),
            budget=self.budget,
        )
        self.assertTrue(
            any(
                item.code == "secret-github-pat"
                for item in report.diagnostics
            )
        )

    def test_dynamic_python_execution_warns(self) -> None:
        report = validate_file(
            CandidateFile(
                path="skeleton/example.py",
                content="value = eval('1 + 1')\n",
            ),
            budget=self.budget,
        )
        self.assertFalse(report.blocking)
        self.assertTrue(
            any(
                item.code == "dynamic-eval"
                and item.severity == "warning"
                for item in report.diagnostics
            )
        )

    def test_missing_final_newline_warns(self) -> None:
        report = validate_file(
            CandidateFile(
                path="docs/example.md",
                content="hello",
            ),
            budget=self.budget,
        )
        self.assertFalse(report.blocking)
        self.assertTrue(
            any(
                item.code == "missing-final-newline"
                for item in report.diagnostics
            )
        )

    def test_oversized_line_blocks(self) -> None:
        report = validate_file(
            CandidateFile(
                path="docs/example.md",
                content=("x" * 32_001) + "\n",
            ),
            budget=self.budget,
        )
        self.assertTrue(report.blocking)
        self.assertTrue(
            any(
                item.code == "oversized-line"
                for item in report.diagnostics
            )
        )

    def test_file_byte_budget_blocks(self) -> None:
        budget = BuildBudget(
            max_total_bytes=4_000,
            max_file_bytes=1_000,
        )
        report = validate_file(
            CandidateFile(
                path="docs/example.md",
                content=("x" * 1_001) + "\n",
            ),
            budget=budget,
        )
        self.assertTrue(
            any(
                item.code == "file-byte-budget"
                for item in report.diagnostics
            )
        )


class CandidateValidationTests(unittest.TestCase):
    def test_exact_planned_coverage_passes(self) -> None:
        files = (
            CandidateFile(
                path="skeleton/example.py",
                content="VALUE = 1\n",
            ),
            CandidateFile(
                path="tests/test_example.py",
                content="def test_value():\n    assert True\n",
            ),
        )
        report = validate_candidate(
            files,
            architecture=architecture(
                "skeleton/example.py",
                "tests/test_example.py",
            ),
            budget=BuildBudget(),
        )
        self.assertTrue(report.publishable)
        self.assertEqual(report.blocking_diagnostics, ())
        self.assertEqual(len(report.fingerprint), 64)
        report.require_publishable()

    def test_missing_planned_file_blocks(self) -> None:
        report = validate_candidate(
            (
                CandidateFile(
                    path="skeleton/example.py",
                    content="VALUE = 1\n",
                ),
            ),
            architecture=architecture(
                "skeleton/example.py",
                "tests/test_example.py",
            ),
            budget=BuildBudget(),
        )
        self.assertFalse(report.publishable)
        self.assertTrue(
            any(
                item.code == "planned-file-missing"
                for item in report.blocking_diagnostics
            )
        )
        with self.assertRaises(BuildValidationError):
            report.require_publishable()

    def test_unplanned_file_blocks(self) -> None:
        report = validate_candidate(
            (
                CandidateFile(
                    path="skeleton/example.py",
                    content="VALUE = 1\n",
                ),
                CandidateFile(
                    path="docs/unplanned.md",
                    content="extra\n",
                ),
            ),
            architecture=architecture(
                "skeleton/example.py",
            ),
            budget=BuildBudget(),
        )
        self.assertTrue(
            any(
                item.code == "unplanned-file"
                for item in report.blocking_diagnostics
            )
        )

    def test_total_byte_budget_blocks(self) -> None:
        budget = BuildBudget(
            max_files=2,
            max_total_bytes=2_000,
            max_file_bytes=1_500,
        )
        report = validate_candidate(
            (
                CandidateFile(
                    path="docs/a.md",
                    content=("a" * 1_100) + "\n",
                ),
                CandidateFile(
                    path="docs/b.md",
                    content=("b" * 1_100) + "\n",
                ),
            ),
            architecture=architecture(
                "docs/a.md",
                "docs/b.md",
            ),
            budget=budget,
        )
        self.assertTrue(
            any(
                item.code == "total-byte-budget"
                for item in report.blocking_diagnostics
            )
        )

    def test_compact_diagnostics_is_bounded(self) -> None:
        report = validate_candidate(
            (
                CandidateFile(
                    path="docs/example.md",
                    content=(
                        "<<<<<<< ours\n"
                        + ("x" * 32_001)
                        + "\n=======\n>>>>>>> theirs\n"
                    ),
                ),
            ),
            architecture=architecture("docs/example.md"),
            budget=BuildBudget(),
        )
        compact = compact_diagnostics(
            report,
            limit=2,
        )
        self.assertLessEqual(len(compact), 2)

    def test_invalid_diagnostic_limit_rejected(self) -> None:
        report = validate_candidate(
            (
                CandidateFile(
                    path="docs/example.md",
                    content="ok\n",
                ),
            ),
            architecture=architecture("docs/example.md"),
            budget=BuildBudget(),
        )
        for value in (0, -1, True, 129):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    compact_diagnostics(report, limit=value)


if __name__ == "__main__":
    unittest.main()
