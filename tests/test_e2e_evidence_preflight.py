"""No-product-execution checks for pre-E2E evidence harness."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/e2e_evidence.py"
ADVANCED = ROOT / "scripts/e2e_advanced_parse.py"

def load_runner():
    spec = importlib.util.spec_from_file_location("e2e_evidence", RUNNER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class TestPreE2EEvidence(unittest.TestCase):
    def test_manifest_has_bounded_offline_and_live_tiers(self):
        suites = load_runner().load_manifest(ROOT / "machine/e2e_suites.json")
        self.assertTrue(any(s["tier"] == "offline" for s in suites))
        self.assertTrue(any(s["tier"] == "live" for s in suites))

    def test_manifest_rejects_duplicate_and_unsafe_paths(self):
        runner = load_runner()
        suites = runner.load_manifest(ROOT / "machine/e2e_suites.json")
        scenarios = [[suites[0], suites[0]], [dict(suites[0], cwd="../")],
                     [dict(suites[0], timeout_seconds=0)],
                     [dict(suites[0], command=["bash", "-c", "echo invalid"])]]
        for scenario in scenarios:
            with tempfile.TemporaryDirectory() as directory:
                file = Path(directory) / "manifest.json"
                file.write_text(json.dumps({"version": 1, "suites": scenario}))
                with self.assertRaises(ValueError):
                    runner.load_manifest(file)

    def test_preflight_records_missing_path_without_running_any_tests(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out"
            manifest = Path(directory) / "manifest.json"
            manifest.write_text(json.dumps({
                "version": 1,
                "suites": [{"id": "fixture", "tier": "offline", "cwd": ".",
                            "required_files": ["this-does-not-exist.e2e"],
                            "timeout_seconds": 2,
                            "command": ["python", "-m", "pytest", "missing.py"]}]
            }))
            result = subprocess.run(
                [sys.executable, str(RUNNER), "--mode", "preflight",
                 "--manifest", str(manifest), "--output-dir", str(output)],
                cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=25
            )
            self.assertEqual(result.returncode, 1)
            report = json.loads((output / "report.json").read_text())
            self.assertEqual(report["mode"], "preflight")
            self.assertEqual(report["executed_suites"], 0)
            self.assertEqual(json.loads((output / "issues.json").read_text())
                             ["issues"][0]["kind"], "missing-file")
            self.assertFalse((output / "logs").exists())

    def test_canonical_redaction(self):
        scrub = load_runner().redactor()
        self.assertNotIn("ABC123", scrub("Authorization: Bearer ABC123"))
        self.assertIn("[REDACTED]", scrub("Authorization: Bearer ABC123"))

    def test_advanced_parser_is_static(self):
        text = ADVANCED.read_text()
        self.assertIn("ast.parse", text)
        self.assertNotIn("importlib.import_module", text)

if __name__ == "__main__":
    unittest.main()
