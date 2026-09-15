from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_workflow_permissions.py"
SPEC = importlib.util.spec_from_file_location("check_workflow_permissions", SCRIPT)
assert SPEC and SPEC.loader
permissions = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(permissions)


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

    def test_read_failure_is_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.yml"
            findings = permissions.violations(missing)
        self.assertTrue(any("FileNotFoundError" in finding for finding in findings))
        self.assertFalse(any(str(missing) in finding for finding in findings))


if __name__ == "__main__":
    unittest.main()
