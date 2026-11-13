"""CI regression contracts for two reproduced November 11 workflow failures.

Keep CodeQL qualification executable on the frontend's supported runtime and
ensure the isolated ecosystem import smoke installs its direct configuration
dependency. This is static workflow-contract coverage, not runtime certification.
"""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


class CiRegressionSuiteContracts(unittest.TestCase):
    def test_codeql_frontend_uses_supported_node_and_preserves_isolation(self):
        source = (WORKFLOWS / "codeql-remediation-branch-qualification.yml").read_text(
            encoding="utf-8"
        )
        self.assertRegex(source, r"node-version:\s*['\"]24['\"]")
        self.assertNotRegex(source, r"node-version:\s*['\"]22['\"]")
        self.assertIn("yarn --cwd frontend install --frozen-lockfile --ignore-scripts", source)
        self.assertIn("persist-credentials: false", source)
        self.assertIn("branches:\n      - 'security/codeql-*'", source)

    def test_codeql_python_is_import_isolated_and_replays_all_alert_contracts(self):
        source = (WORKFLOWS / "codeql-remediation-branch-qualification.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("python -m pytest --noconftest --import-mode=importlib --rootdir=. -q", source)
        self.assertIn("PYTEST_DISABLE_PLUGIN_AUTOLOAD: '1'", source)
        for path in (
            "tests/test_codeql_lineage_contract_20261111.py",
            "tests/test_full_security_alert_inventory_20261111.py",
            "tests/test_codeql_all_151_source_contracts_20261111.py",
            "backend/tests/test_codeql_exception_boundary_20261111.py",
            "backend/tests/test_public_exception_route_security.py",
        ):
            with self.subTest(path=path):
                self.assertIn(path, source)
                self.assertTrue((ROOT / path).is_file())
        self.assertIn("cancel-in-progress: true", source)

    def test_flat_ecosystem_smoke_installs_production_settings_and_preserves_both_layouts(self):
        source = (WORKFLOWS / "ecosystem-api-import-qualification.yml").read_text(
            encoding="utf-8"
        )
        requirements = (ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("pydantic-settings==2.16.2", source)
        self.assertIn("pydantic-settings==2.16.2", requirements)
        self.assertIn("python -m unittest discover -s backend/tests -p test_ecosystem_import_layout_20261111.py -v", source)
        self.assertIn("python scripts/check_repository_dynamic_import_safety.py", source)
        self.assertIn("python scripts/check_ai_file_tree.py", source)
        smoke = (ROOT / "backend/tests/test_ecosystem_import_layout_20261111.py").read_text(
            encoding="utf-8"
        )
        for label in ("test_flat_production_router", "test_source_checkout_router"):
            self.assertIn("def " + label, smoke)
        self.assertIn("persist-credentials: false", source)


if __name__ == "__main__":
    unittest.main()
