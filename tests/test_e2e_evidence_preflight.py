"""No-product-execution checks for pre-E2E evidence harness."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

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


    def test_aggregate_fail_closed_when_receipts_are_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            artifacts = Path(directory) / "shards"
            artifacts.mkdir()
            output = Path(directory) / "aggregate"
            completed = subprocess.run(
                [sys.executable, str(ROOT / "scripts/e2e_merge_evidence.py"),
                 "--artifacts", str(artifacts), "--output-dir", str(output)],
                cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=25
            )
            self.assertEqual(completed.returncode, 1)
            receipt = json.loads((output / "aggregate.json").read_text())
            self.assertFalse(receipt["passed"])
            self.assertTrue(any(x["kind"] == "missing-shard"
                                for x in receipt["issues"]))

    def test_aggregate_requires_one_head_and_all_manifest_shards(self):
        with tempfile.TemporaryDirectory() as directory:
            artifacts = Path(directory) / "shards"
            artifacts.mkdir()
            expected = [s["id"] for s in load_runner().load_manifest(ROOT / "machine/e2e_suites.json")
                        if s["tier"] == "offline"]
            for suite in expected:
                folder = artifacts / ("e2e-" + suite)
                folder.mkdir()
                (folder / "report.json").write_text(json.dumps({
                    "schema": "skeleton.e2e.evidence.v1", "mode": "offline-e2e",
                    "head_sha": "a" * 40, "run_id": "fixture",
                    "status": "passed", "issues_count": 0, "executed_suites": 1,
                    "suites": [{"id": suite, "status": "passed", "duration_seconds": 1,
                                "exit_code": 0, "timed_out": False}]
                }))
                (folder / "issues.json").write_text(json.dumps({
                    "schema": "skeleton.e2e.issues.v1", "issues": []
                }))
            output = Path(directory) / "aggregate"
            completed = subprocess.run(
                [sys.executable, str(ROOT / "scripts/e2e_merge_evidence.py"),
                 "--artifacts", str(artifacts), "--output-dir", str(output)],
                cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=25
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            receipt = json.loads((output / "aggregate.json").read_text())
            self.assertTrue(receipt["passed"])
            self.assertEqual(receipt["exact_head"], "a" * 40)
            first = artifacts / ("e2e-" + expected[0]) / "report.json"
            original = first.read_text()
            for change in ("missing-head", "nonzero-exit", "timeout", "report-failed", "bad-count"):
                with self.subTest(change=change):
                    payload = json.loads(original)
                    if change == "missing-head":
                        del payload["head_sha"]
                    elif change == "nonzero-exit":
                        payload["suites"][0]["exit_code"] = 1
                    elif change == "timeout":
                        payload["suites"][0]["timed_out"] = True
                    elif change == "report-failed":
                        payload["status"] = "failed"
                    else:
                        payload["issues_count"] = 1
                    first.write_text(json.dumps(payload))
                    completed = subprocess.run(
                        [sys.executable, str(ROOT / "scripts/e2e_merge_evidence.py"),
                         "--artifacts", str(artifacts), "--output-dir", str(output)],
                        cwd=ROOT, capture_output=True, timeout=25)
                    self.assertEqual(completed.returncode, 1)
                    self.assertFalse(json.loads((output / "aggregate.json").read_text())["passed"])

    def test_offline_default_excludes_live_and_nonpytest_python_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "manifest.json"
            suites = [{"id": tier, "tier": tier, "cwd": ".", "required_files": [],
                       "timeout_seconds": 5, "command": ["python", "-c", "print('fixture completed')"]}
                      for tier in ("offline", "live")]
            manifest.write_text(json.dumps({"version": 1, "suites": suites}))
            command = [sys.executable, str(RUNNER), "--mode", "offline-e2e",
                       "--manifest", str(manifest)]
            completed = subprocess.run(command + ["--output-dir", str(root / "default")],
                                       cwd=ROOT, capture_output=True, timeout=25)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            report = json.loads((root / "default/report.json").read_text())
            self.assertEqual([s["id"] for s in report["suites"]], ["offline"])
            rejected = subprocess.run(command + ["--suite", "offline", "--suite", "live",
                                     "--output-dir", str(root / "rejected")],
                                      cwd=ROOT, capture_output=True, timeout=25)
            self.assertEqual(rejected.returncode, 2)
            self.assertFalse((root / "rejected/logs").exists())

    def test_empty_and_skipped_junit_are_unverified(self):
        runner = load_runner()
        for body, kind in (("<testsuite/>", "empty-junit"),
                           ('<testsuite><testcase name="playtest"><skipped message="missing engine"/></testcase></testsuite>',
                            "unverified-test")):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                output = Path(directory)
                recorder = runner.Recorder(output, lambda value: value)
                raw = output / "raw.xml"
                raw.write_text(body)
                self.assertEqual(runner.parse_junit(raw, "fixture", recorder), 1)
                self.assertEqual(recorder.issues[0]["kind"], kind)
                recorder.finish("offline-e2e")

    def test_confirmed_syntax_error_blocks_static_preflight(self):
        spec = importlib.util.spec_from_file_location("e2e_advanced", ADVANCED)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "backend/tests").mkdir(parents=True)
            (root / "backend/tests/live_service_tests.json").write_text('{"tests": []}')
            (root / "test_broken.py").write_text('def test_broken(:\n    pass\n')
            with patch.object(module, "ROOT", root), patch.object(module, "tracked", return_value=["test_broken.py"]), \
                    patch.object(sys, "argv", [str(ADVANCED), "--output-dir", str(root / "out")]):
                self.assertEqual(module.main(), 2)

if __name__ == "__main__":
    unittest.main()
