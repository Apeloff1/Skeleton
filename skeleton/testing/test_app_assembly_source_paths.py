"""Regression guard for canonical frontend source paths referenced by assembly contracts.

The product frontend keeps its implementation under frontend/src; stale
references to the pre-migration frontend/utils and frontend/components
directories broke the fail-closed app-assembly validator.
"""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RESOLVER = "frontend/src/utils/apiBase.ts"
LAUNCH = "frontend/src/components/LaunchCascade.tsx"
BOOT = "frontend/src/components/BootLauncher.tsx"
ROUTES = "frontend/src/utils/routeRegistry.ts"

CANONICAL_FILES = (RESOLVER, LAUNCH, BOOT, ROUTES)
CONTRACT_FILES = (
    "machine/manifest.json",
    "machine/architecture.json",
    "skeleton/app/manifest.json",
    "docs/ARCHITECTURE_MAP.md",
    "scripts/check_app_assembly.py",
)


class AppAssemblySourcePathsTests(unittest.TestCase):
    def test_canonical_frontend_files_exist(self) -> None:
        for path in CANONICAL_FILES:
            with self.subTest(path=path):
                self.assertTrue((ROOT / path).is_file(), f"missing canonical source: {path}")

    def test_contracts_and_validator_use_real_resolver_path(self) -> None:
        for path in CONTRACT_FILES:
            with self.subTest(path=path):
                text = (ROOT / path).read_text(encoding="utf-8")
                self.assertIn(RESOLVER, text)
                self.assertNotIn("frontend/utils/apiBase.ts", text)

    def test_app_assembly_uses_real_launch_and_route_files(self) -> None:
        validator = (ROOT / "scripts/check_app_assembly.py").read_text(encoding="utf-8")
        for path in (LAUNCH, BOOT, ROUTES):
            with self.subTest(path=path):
                self.assertIn(f'read("{path}")', validator)
        for obsolete in (
            "frontend/components/LaunchCascade.tsx",
            "frontend/components/BootLauncher.tsx",
            "frontend/utils/routeRegistry.ts",
        ):
            with self.subTest(obsolete=obsolete):
                self.assertNotIn(f'read("{obsolete}")', validator)

    def test_api_client_consumes_canonical_resolver(self) -> None:
        resolver = (ROOT / RESOLVER).read_text(encoding="utf-8")
        client = (ROOT / "frontend/src/utils/apiClient.ts").read_text(encoding="utf-8")
        self.assertIn("export const API_BASE", resolver)
        self.assertIn("export const SKELETON_API_BASE", resolver)
        self.assertIn("from './apiBase'", client)


if __name__ == "__main__":
    unittest.main()
