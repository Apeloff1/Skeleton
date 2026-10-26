"""Regression for canonical quality/automation CI dependency floors."""
from __future__ import annotations

import unittest

from scripts.check_ci_runtime_dependency_parity import CHECKS, ROOT, validate, validate_source


class CiRuntimeDependencyFloorContract(unittest.TestCase):
    def test_current_workflow_versions_match_supported_floors(self) -> None:
        self.assertEqual(validate(), [])

    def test_missing_install_step_fails_closed(self) -> None:
        self.assertTrue(validate_source("merge-readiness.yml", "name: Merge Readiness\n"))

    def test_old_unit_dependencies_are_rejected(self) -> None:
        name = "merge-readiness.yml"
        path = ROOT / ".github" / "workflows" / name
        content = path.read_text(encoding="utf-8")
        old = content.replace('"httpx>=0.28.1,<1"', '"httpx>=0.27,<1"')
        self.assertNotEqual(old, content)
        issues = validate_source(name, old)
        self.assertTrue(any("httpx>=0.28.1,<1" in issue for issue in issues))

    def test_old_backend_quality_floor_is_rejected(self) -> None:
        name = "backend-quality.yml"
        content = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
        old = content.replace('"pydantic-settings>=2.15.0,<3"',
                              '"pydantic-settings>=2.1,<3"', 1)
        self.assertNotEqual(old, content)
        self.assertTrue(any("pydantic-settings>=2.15.0" in issue
                            for issue in validate_source(name, old)))

    def test_ruff_patch_floor_is_covered_by_security_gate(self) -> None:
        marker = ("merge-readiness.yml", "Install focused quality dependencies")
        self.assertIn("ruff==0.17.2", CHECKS[marker])


if __name__ == "__main__":
    unittest.main()
