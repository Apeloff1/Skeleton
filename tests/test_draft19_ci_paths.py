"""Regression acceptance for literal Draft19 CI path/selector qualification."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.check_draft19_ci_paths import validate_ci_paths


class Draft19CIPathTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.workflow = self.root / ".github/workflows/draft19-gguf-source-qualification.yml"
        self.workflow.parent.mkdir(parents=True)
        self.source = self.root / "tests/test_sample.py"
        self.source.parent.mkdir()
        self.source.write_text(
            "def test_real():\n    assert True\n\n"
            "def test_other():\n    assert False\n", encoding="utf-8"
        )

    def set_workflow(self, body):
        self.workflow.write_text(
            "name: Admission\njobs:\n  checks:\n    steps:\n      - run: |\n" + body,
            encoding="utf-8",
        )

    def test_valid_standalone_and_function_selectors_are_accepted(self):
        self.set_workflow(
            "          python -m py_compile tests/test_sample.py\n"
            "          python -m pytest tests/test_sample.py::test_real\n"
            "          python -m pytest tests/test_sample.py::test_other\n"
        )
        self.assertEqual(validate_ci_paths(self.root), ())

    def test_missing_source_is_not_silently_skipped(self):
        self.set_workflow("          python -m pytest tests/missing.py\n")
        self.assertIn("missing source: tests/missing.py",
                      validate_ci_paths(self.root))

    def test_renamed_selector_is_denied(self):
        self.set_workflow(
            "          python -m pytest tests/test_sample.py::test_archived\n"
        )
        self.assertIn(
            "missing pytest selector: tests/test_sample.py::test_archived",
            validate_ci_paths(self.root),
        )

    def test_duplicate_selector_is_denied(self):
        self.set_workflow(
            "          python -m pytest tests/test_sample.py::test_real\n"
            "          python -m pytest tests/test_sample.py::test_real\n"
        )
        self.assertTrue(any("duplicate pytest selector" in error
                            for error in validate_ci_paths(self.root)))

    def test_no_source_references_is_a_failure(self):
        self.set_workflow("          echo no-tests\n")
        self.assertEqual(validate_ci_paths(self.root),
                         ("workflow has no literal Python source references",))

    def test_symlinked_source_is_denied(self):
        link = self.root / "tests/test_alias.py"
        link.symlink_to(self.source)
        self.set_workflow("          python -m pytest tests/test_alias.py\n")
        self.assertIn("symbolic source path: tests/test_alias.py",
                      validate_ci_paths(self.root))

    def test_invalid_python_does_not_qualify_selector(self):
        self.source.write_text("def test_real(:\n", encoding="utf-8")
        self.set_workflow(
            "          python -m pytest tests/test_sample.py::test_real\n"
        )
        self.assertIn("test source cannot be parsed: tests/test_sample.py",
                      validate_ci_paths(self.root))

    def test_invalid_workflow_path_is_rejected(self):
        self.set_workflow("          python -m pytest tests/test_sample.py\n")
        self.assertEqual(
            validate_ci_paths(self.root, "../another.yml"),
            ("invalid workflow path",),
        )

    def test_workflow_read_budget_fails_closed(self):
        self.workflow.write_bytes(b"x" * (128 * 1024 + 1))
        self.assertEqual(
            validate_ci_paths(self.root),
            ("workflow exceeds path-check budget",),
        )


if __name__ == "__main__":
    unittest.main()
