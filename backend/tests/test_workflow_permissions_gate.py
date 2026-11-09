from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts import check_workflow_permissions as permissions


class WorkflowPermissionGateTests(unittest.TestCase):
    def test_allows_workflow_deny_all_with_narrow_job_write(self) -> None:
        text = """name: safe
permissions: {}
jobs:
  mutate:
    permissions:
      contents: write
      pull-requests: read
"""
        self.assertEqual(permissions.violations_from_text("safe.yml", text), [])

    def test_allows_explicit_read_only_workflow_ceiling(self) -> None:
        text = """name: safe
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
"""
        self.assertEqual(permissions.violations_from_text("safe.yml", text), [])

    def test_rejects_missing_top_level_permissions(self) -> None:
        text = """name: unsafe
jobs:
  test:
    permissions:
      contents: read
"""
        findings = permissions.violations_from_text("unsafe.yml", text)
        self.assertTrue(any("missing top-level permissions" in finding for finding in findings))

    def test_rejects_workflow_wide_write(self) -> None:
        text = """name: unsafe
permissions:
  contents: read
  issues: write
jobs:
  test:
    runs-on: ubuntu-latest
"""
        findings = permissions.violations_from_text("unsafe.yml", text)
        self.assertTrue(any("workflow-wide 'issues: write'" in finding for finding in findings))

    def test_rejects_write_all_at_job_scope(self) -> None:
        text = """name: unsafe
permissions: {}
jobs:
  mutate:
    permissions: write-all
"""
        findings = permissions.violations_from_text("unsafe.yml", text)
        self.assertTrue(any("write-all" in finding for finding in findings))

    def test_rejects_read_all_at_job_scope(self) -> None:
        text = """name: unsafe
permissions: {}
jobs:
  inspect:
    permissions: read-all
"""
        findings = permissions.violations_from_text("unsafe.yml", text)
        self.assertTrue(any("read-all" in finding for finding in findings))

    def test_rejects_double_quoted_write_all_at_job_scope(self) -> None:
        text = """name: unsafe
permissions: {}
jobs:
  mutate:
    permissions: "write-all"
"""
        findings = permissions.violations_from_text("unsafe.yml", text)
        self.assertTrue(any("write-all" in finding for finding in findings))

    def test_rejects_single_quoted_read_all_at_job_scope(self) -> None:
        text = """name: unsafe
permissions: {}
jobs:
  inspect:
    permissions: 'read-all'
"""
        findings = permissions.violations_from_text("unsafe.yml", text)
        self.assertTrue(any("read-all" in finding for finding in findings))

    def test_rejects_opaque_top_level_flow_mapping(self) -> None:
        text = """name: unsafe
permissions: {contents: read}
jobs:
  test:
    runs-on: ubuntu-latest
"""
        findings = permissions.violations_from_text("unsafe.yml", text)
        self.assertTrue(any("opaque/inline" in finding for finding in findings))

    def test_rejects_duplicate_top_level_permissions(self) -> None:
        text = """name: unsafe
permissions: {}
permissions:
  contents: read
jobs: {}
"""
        findings = permissions.violations_from_text("unsafe.yml", text)
        self.assertTrue(any("multiple top-level" in finding for finding in findings))

    def test_rejects_symlinked_workflow_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target.yml"
            target.write_text("name: target\npermissions: {}\njobs: {}\n", encoding="utf-8")
            link = root / "linked.yml"
            try:
                link.symlink_to(target)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"symlinks unavailable: {type(exc).__name__}")

            findings = permissions.violations(link)

        self.assertEqual(findings, ["linked.yml: workflow files must not be symlinks"])

    def test_rejects_symlinked_workflow_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "real-workflows"
            target.mkdir()
            (target / "safe.yml").write_text(
                "name: safe\npermissions: {}\njobs: {}\n", encoding="utf-8"
            )
            link = root / "workflows"
            try:
                link.symlink_to(target, target_is_directory=True)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"directory symlinks unavailable: {type(exc).__name__}")

            with mock.patch.object(permissions, "WORKFLOW_DIR", link):
                self.assertEqual(permissions.main(), 1)

    def test_read_failure_is_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.yml"
            findings = permissions.violations(missing)
        self.assertTrue(any("FileNotFoundError" in finding for finding in findings))
        self.assertFalse(any(str(missing) in finding for finding in findings))


if __name__ == "__main__":
    unittest.main()
