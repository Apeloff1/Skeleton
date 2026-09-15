from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_package_lifecycle.py"
SPEC = importlib.util.spec_from_file_location("check_package_lifecycle", SCRIPT)
assert SPEC and SPEC.loader
lifecycle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lifecycle)


class PackageLifecyclePolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / "frontend").mkdir(parents=True)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _write_scripts(self, scripts: dict[str, object]) -> None:
        payload = {"name": "frontend", "scripts": scripts}
        (self.root / "frontend" / "package.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

    def _violations(self) -> list[str]:
        with mock.patch.object(lifecycle, "REPO_ROOT", self.root):
            with mock.patch.object(
                lifecycle,
                "tracked_package_files",
                return_value=["frontend/package.json"],
            ):
                return lifecycle.violations()

    def test_allows_exact_approved_postinstall(self) -> None:
        self._write_scripts(
            {"postinstall": "node ./scripts/patch-node-modules.js", "lint": "expo lint"}
        )
        self.assertEqual(self._violations(), [])

    def test_rejects_unapproved_postinstall(self) -> None:
        self._write_scripts({"postinstall": "node ./scripts/other.js"})
        findings = self._violations()
        self.assertTrue(any("unapproved lifecycle hook" in finding for finding in findings))

    def test_rejects_new_preinstall_hook(self) -> None:
        self._write_scripts({"preinstall": "node ./scripts/bootstrap.js"})
        findings = self._violations()
        self.assertTrue(any("preinstall" in finding for finding in findings))

    def test_rejects_non_string_lifecycle_command(self) -> None:
        self._write_scripts({"postinstall": ["node", "script.js"]})
        findings = self._violations()
        self.assertTrue(any("must be a string" in finding for finding in findings))

    def test_rejects_malformed_manifest_cleanly(self) -> None:
        (self.root / "frontend" / "package.json").write_text("{broken", encoding="utf-8")
        findings = self._violations()
        self.assertTrue(any("cannot safely parse manifest" in finding for finding in findings))


if __name__ == "__main__":
    unittest.main()
