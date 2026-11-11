"""Regression for trusted-base merge-hold CLI import and workflow custody."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/pr-merge-hold.yml"


class MergeHoldEntrypointRegression(unittest.TestCase):
    def test_module_entrypoint_imports_from_checkout_without_pythonpath(self) -> None:
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env.pop("GITHUB_EVENT_NAME", None)
        env.pop("GITHUB_TOKEN", None)
        proc = subprocess.run(
            [sys.executable, "-m", "scripts.check_pr_merge_hold"],
            cwd=ROOT, env=env, capture_output=True, text=True, timeout=15,
            check=False,
        )
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("trusted pull_request_target event required", proc.stderr)
        self.assertNotIn("ModuleNotFoundError", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)

    def test_privileged_workflow_only_executes_trusted_base(self) -> None:
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("pull_request_target:", source)
        self.assertIn("ref: ${{ github.event.pull_request.base.sha }}", source)
        self.assertIn("persist-credentials: false", source)
        self.assertIn("python -m scripts.check_pr_merge_hold", source)
        self.assertNotIn("python scripts/check_pr_merge_hold.py", source)
        self.assertNotIn("ref: ${{ github.event.pull_request.head.sha }}", source)
        self.assertNotIn("ref: ${{ github.head_ref }}", source)
        self.assertIn("pull-requests: read", source)
        self.assertNotIn("pull-requests: write", source)

    def test_untrusted_event_cannot_activate_gate(self) -> None:
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env["GITHUB_EVENT_NAME"] = "pull_request"
        env["GITHUB_REPOSITORY"] = "Apeloff1/Skeleton"
        env.pop("GITHUB_TOKEN", None)
        proc = subprocess.run(
            [sys.executable, "-m", "scripts.check_pr_merge_hold"],
            cwd=ROOT, env=env, capture_output=True, text=True, timeout=15,
            check=False,
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("trusted pull_request_target event required", proc.stderr)


if __name__ == "__main__":
    unittest.main()
