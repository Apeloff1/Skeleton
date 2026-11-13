"""Hermetic CI installer contract: retries APT/DNS failure without skipping dependencies."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ci_playwright_install.sh"


class PlaywrightInstallContractTests(unittest.TestCase):
    def run_installer(self, *, failures=0, npm_failure=False, version="1.56.1"):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            log = root / "commands.log"
            counter = root / "attempts"
            commands = {
                "npm": """#!/bin/sh
printf 'npm:%s\\n' "$*" >> "$MOCK_LOG"
if [ "$MOCK_NPM_FAIL" = 1 ]; then exit 67; fi
""",
                "npx": """#!/bin/sh
printf 'npx:%s\\n' "$*" >> "$MOCK_LOG"
count=0
if [ -f "$MOCK_COUNT" ]; then count=$(cat "$MOCK_COUNT"); fi
count=$((count + 1))
printf '%s' "$count" > "$MOCK_COUNT"
if [ "$count" -le "$MOCK_NPX_FAILS" ]; then exit 68; fi
""",
                "sleep": """#!/bin/sh
printf 'sleep:%s\\n' "$*" >> "$MOCK_LOG"
""",
            }
            for name, body in commands.items():
                executable = root / name
                executable.write_text(body, encoding="utf-8")
                executable.chmod(0o700)
            env = {
                **os.environ,
                "PATH": f"{root}:{os.environ.get('PATH', '')}",
                "MOCK_LOG": str(log),
                "MOCK_COUNT": str(counter),
                "MOCK_NPX_FAILS": str(failures),
                "MOCK_NPM_FAIL": "1" if npm_failure else "0",
            }
            if version is None:
                env.pop("PLAYWRIGHT_VERSION", None)
            else:
                env["PLAYWRIGHT_VERSION"] = version
            result = subprocess.run(
                ["bash", str(SCRIPT)], cwd=root, env=env,
                text=True, capture_output=True, check=False, timeout=15,
            )
            lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
            return result, lines

    def test_success_installs_pinned_package_and_all_chromium_dependencies(self):
        result, lines = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(lines, [
            "npm:install --no-save --no-package-lock --no-audit --no-fund --ignore-scripts @playwright/test@1.56.1",
            "npx:--no-install playwright install --with-deps chromium",
        ])

    def test_transient_failure_retries_without_skipping_dependency_install(self):
        result, lines = self.run_installer(failures=2)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sum(line.startswith("npm:") for line in lines), 1)
        self.assertEqual(sum(line == "npx:--no-install playwright install --with-deps chromium"
                             for line in lines), 3)
        self.assertEqual([line for line in lines if line.startswith("sleep:")],
                         ["sleep:15", "sleep:30"])

    def test_persistent_failure_fails_closed_after_bounded_attempts(self):
        result, lines = self.run_installer(failures=10)
        self.assertEqual(result.returncode, 1)
        self.assertIn("all 3 dependency-install attempts failed", result.stderr)
        self.assertEqual(sum(line.startswith("npx:") for line in lines), 3)
        self.assertEqual([line for line in lines if line.startswith("sleep:")],
                         ["sleep:15", "sleep:30"])

    def test_npm_failure_is_not_misreported_as_browser_success(self):
        result, lines = self.run_installer(npm_failure=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("npm:"))

    def test_workflow_wires_pinned_installer_and_unskipped_contract(self):
        workflow = (SCRIPT.parents[1] / ".github" / "workflows" /
                    "app-foundation-e2e.yml").read_text(encoding="utf-8")
        self.assertIn('PLAYWRIGHT_VERSION: "1.56.1"', workflow)
        self.assertIn("bash ../../scripts/ci_playwright_install.sh", workflow)
        self.assertIn("playwright-install-contract:", workflow)
        self.assertIn("python -m unittest discover -s tests -p test_ci_playwright_install.py -q",
                      workflow)
        self.assertIn("npx --no-install playwright install --with-deps chromium",
                      SCRIPT.read_text(encoding="utf-8"))

    def test_invalid_versions_are_rejected_before_any_install(self):
        for version in (None, "", "latest", "1.56.1;echo unsafe", "1.56.1\n"):
            with self.subTest(version=version):
                result, lines = self.run_installer(version=version)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(lines, [])


if __name__ == "__main__":
    unittest.main()
