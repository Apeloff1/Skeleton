"""Deterministic evidence checks for the tracked stub/truncation classifier."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.classify_repo_stubs import classify, markers, owner, severity


class ClassifyRepositoryStubsTests(unittest.TestCase):
    def test_python_executable_raise_and_placeholder_are_distinct(self) -> None:
        source = "def missing():\n    raise NotImplementedError()\ndef placeholder():\n    pass\n"
        self.assertIn((2, "raise_not_implemented"), markers("app.py", source))
        self.assertIn((4, "empty_statement"), markers("app.py", source))

    def test_typescript_executable_throw(self) -> None:
        self.assertIn(
            (1, "throw_not_implemented"),
            markers("app.ts", "throw new Error('Not implemented');"),
        )

    def test_rust_and_java_unimplemented_constructs(self) -> None:
        self.assertIn(
            (1, "unsupported_operation_candidate"),
            markers("engine.rs", "fn play() { unimplemented!() }"),
        )
        self.assertIn(
            (1, "unsupported_operation_candidate"),
            markers("Runtime.java", 'throw new UnsupportedOperationException("pending");'),
        )

    def test_historical_and_fixture_markers_are_not_automatic_blockers(self) -> None:
        self.assertEqual(owner("satellites/branch-snapshots/old/a.py"), "historical_snapshot")
        self.assertEqual(owner("skeleton/testing/test_stub.py"), "test_or_fixture")
        self.assertEqual(severity("historical_snapshot", "raise_not_implemented"), "context_only")
        self.assertEqual(severity("production_candidate", "raise_not_implemented"), "implementation_review")

    def test_truncation_marker_is_recorded_by_line(self) -> None:
        self.assertIn((2, "truncation_marker"), markers("logs.md", "first\n[truncated]\n"))

    def test_complete_git_blob_scan_preserves_full_findings(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "frontend" / "app").mkdir(parents=True)
            (root / "tests").mkdir()
            (root / "frontend" / "app" / "unfinished.ts").write_text(
                "throw new Error('Not implemented');\n", encoding="utf-8"
            )
            (root / "tests" / "example.py").write_text(
                "def fixture():\n    pass\n", encoding="utf-8"
            )
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run(
                ["git", "-C", str(root), "-c", "user.email=fixture@example.invalid",
                 "-c", "user.name=Fixture", "commit", "-qm", "fixture"],
                check=True,
            )
            before = Path.cwd()
            try:
                os.chdir(root)
                result = classify("HEAD", root / "out.jsonl", root / "summary.json")
            finally:
                os.chdir(before)
            findings = [json.loads(line) for line in (root / "out.jsonl").read_text().splitlines()]
            self.assertTrue(result["inventory_complete"])
            self.assertEqual(result["counts"]["tracked_text_paths"], 2)
            self.assertTrue(any(
                item["kind"] == "throw_not_implemented"
                and item["severity"] == "implementation_review"
                for item in findings
            ))
            self.assertTrue(any(
                item["category"] == "test_or_fixture"
                and item["severity"] == "context_only"
                for item in findings
            ))


if __name__ == "__main__":
    unittest.main()
