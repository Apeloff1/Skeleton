"""Process-level E2E suite: ``python3 -m skeleton dev ...``.

Asserts real exit codes and stdout contracts for the dev CLI the way CI and
humans invoke it. Known defects are pinned with ``expectedFailure`` so they
show up when fixed.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _cli_e2e_support import PASS_BANNER, first_json, json_documents, run_module  # noqa: E402


class ModuleExitCodeTests(unittest.TestCase):
    def assertExit(self, argv, code):
        proc = run_module(argv)
        self.assertEqual(proc.returncode, code, f"{argv}: stdout={proc.stdout[-400:]!r} stderr={proc.stderr[-400:]!r}")
        return proc

    def test_help_exits_zero(self):
        proc = self.assertExit(["--help"], 0)
        self.assertIn("skeleton dev", proc.stdout)

    def test_unknown_command_exits_one(self):
        proc = self.assertExit(["no-such-cmd"], 1)
        self.assertIn("Unknown dev command", proc.stderr)
        self.assertEqual(first_json(proc.stdout), {"error": "Unknown dev command: no-such-cmd"})

    def test_bad_flag_exits_two(self):
        proc = self.assertExit(["doctor", "--no-such-flag"], 2)
        self.assertIn("unrecognized arguments", proc.stderr)

    def test_passing_gates_exit_zero(self):
        for argv in (["doctor", "--gates", "--json"], ["cockpit", "--gates"], ["bridge"], ["regen", "--allow-empty"]):
            with self.subTest(argv=argv):
                proc = self.assertExit(argv, 0)
                self.assertEqual(first_json(proc.stdout)["banner"], PASS_BANNER)

    def test_fail_closed_gate_exits_one(self):
        proc = self.assertExit(["regen"], 1)
        self.assertEqual(first_json(proc.stdout)["ok"], 0)

    def test_unknown_pipeline_path_exits_one(self):
        proc = self.assertExit(["stu-tools", "--paths", "bogus", "--json"], 1)
        self.assertIn("suite.empty", first_json(proc.stdout)["verdict"]["blocking"])

    def test_ci_bundle_exits_zero(self):
        proc = self.assertExit(["stu-tools", "--ci-bundle", "--json"], 0)
        self.assertEqual(first_json(proc.stdout)["kind"], "stu-tools-ci-bundle")

    def test_visualize_without_blueprint_exits_one(self):
        self.assertExit(["visualize"], 1)

    def test_validate_missing_path_exits_one(self):
        self.assertExit(["validate", "/nonexistent/skeleton/path"], 1)

    def test_snapshot_round_trip_exit_codes(self):
        with tempfile.TemporaryDirectory() as root:
            doc = Path(root) / "doc.txt"
            doc.write_text("cockpit doctor bridge regen", encoding="utf-8")
            snap = self.assertExit(["snapshot", "--root", root, "--name", "proc", "--ingest", str(doc)], 0)
            self.assertEqual(json_documents(snap.stdout)[-1]["action"], "snapshot")
            listed = self.assertExit(["snapshots", "--root", root], 0)
            self.assertGreaterEqual(json_documents(listed.stdout)[-1]["count"], 1)
            restored = self.assertExit(["restore", "--root", root, "--name", "proc"], 0)
            payload = json_documents(restored.stdout)[-1]
            self.assertEqual(payload["restored"], json_documents(snap.stdout)[-1]["planes"])


class ModuleStdoutContractTests(unittest.TestCase):
    def test_json_payloads_are_identical_when_duplicated(self):
        proc = run_module(["doctor", "--gates", "--json"])
        docs = json_documents(proc.stdout)
        self.assertTrue(docs)
        self.assertTrue(all(d == docs[0] for d in docs))

    @unittest.expectedFailure
    def test_json_flag_emits_single_document(self):
        # BUG: commands print their own JSON, then skeleton/__main__.py prints the
        # returned mapping again, so `--json` stdout is two concatenated documents
        # and not parseable with json.loads. Remove expectedFailure once fixed.
        import json

        proc = run_module(["doctor", "--gates", "--json"])
        json.loads(proc.stdout)

    @unittest.expectedFailure
    def test_help_does_not_print_status_mapping(self):
        # BUG: `python -m skeleton dev --help` prints {"status": "help_shown"}
        # after the help text (skeleton.developer.cli.main suppresses it; the
        # skeleton/__main__.py dispatcher does not).
        proc = run_module(["--help"])
        self.assertNotIn("help_shown", proc.stdout)


if __name__ == "__main__":
    unittest.main()
