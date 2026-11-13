"""Adversarial tests for source-scoped Dragon jobs inside required CI."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.check_dragon_workflow_scope import (
    MAX_DIFF_BYTES, _run, classify, decide, exact_head_paths, main,
)
from scripts.check_ci_workflow_tiers import audit

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
HEAD = "a" * 40
BASE = "b" * 40


class DragonScopeTests(unittest.TestCase):
    def test_unrelated_changes_do_not_consume_specialist_runners(self) -> None:
        self.assertEqual(classify(["docs/README.md", "skeleton/forge/other.py"]),
                         {"backend": False, "source": False, "frontend": False})

    def test_crawler_change_requires_backend_and_source(self) -> None:
        self.assertEqual(classify(["skeleton/ai/webcrawler/core.py"]),
                         {"backend": True, "source": True, "frontend": False})

    def test_frontend_change_requires_client_regression(self) -> None:
        self.assertEqual(classify(["frontend/src/product/crawlerClient.ts"]),
                         {"backend": False, "source": False, "frontend": True})

    def test_authenticated_backend_adapter_requires_both_python_lanes(self) -> None:
        self.assertEqual(classify(["backend/core/dragon_crawler.py"]),
                         {"backend": True, "source": True, "frontend": False})

    def test_full_workflow_custody_change_runs_every_lane(self) -> None:
        for path in (
            ".github/workflows/dragon-campaign-source-tests.yml",
            ".github/workflows/dragon-campaign-frontend-checks.yml",
            ".github/workflows/dragon-atlas-backend-bridge.yml",
            ".github/workflows/backend-quality.yml",
            "scripts/check_dragon_workflow_scope.py",
        ):
            self.assertEqual(classify([path]),
                             {"backend": True, "source": True, "frontend": True},
                             path)

    def test_negative_path_inventory_cannot_skip_any_test(self) -> None:
        for path in ("", "/absolute/path.py", "unsafe\x00filename.py"):
            self.assertTrue(all(classify([path]).values()))

    def test_changed_file_union_retains_all_required_suites(self) -> None:
        self.assertEqual(
            classify(["docs/README.md",
                      "tests/test_ai_webcrawler_dragon_capture_rights.py",
                      "frontend/src/product/crawlerClient.ts"]),
            {"backend": True, "source": True, "frontend": True},
        )

    def test_invalid_commit_identity_is_rejected_before_subprocess(self) -> None:
        with patch("scripts.check_dragon_workflow_scope.subprocess.run") as command:
            with self.assertRaisesRegex(ValueError, "40-hex"):
                exact_head_paths(base="../../bad", head=HEAD)
            with self.assertRaisesRegex(ValueError, "40-hex"):
                exact_head_paths(base=BASE, head="bad")
            command.assert_not_called()

    def test_wrong_checkout_head_fails_closed(self) -> None:
        with patch("scripts.check_dragon_workflow_scope._run", return_value=b"c" * 40):
            selection, reason = decide(base=BASE, head=HEAD)
            self.assertTrue(all(selection.values()))
            self.assertIn("fail-closed", reason)

    def test_git_error_fails_closed(self) -> None:
        with patch("scripts.check_dragon_workflow_scope._run",
                   side_effect=subprocess.CalledProcessError(128, ["git"])):
            selection, reason = decide(base=BASE, head=HEAD)
            self.assertTrue(all(selection.values()))
            self.assertIn("CalledProcessError", reason)

    def test_timeout_fails_closed(self) -> None:
        with patch("scripts.check_dragon_workflow_scope._run",
                   side_effect=subprocess.TimeoutExpired(["git"], 90)):
            selection, _ = decide(base=BASE, head=HEAD)
            self.assertTrue(all(selection.values()))

    def test_full_nul_delimited_diff_and_commit_identity(self) -> None:
        payload = b"backend/core/dragon_crawler.py\x00deleted/file.py\x00"
        with patch("scripts.check_dragon_workflow_scope._run",
                   side_effect=[HEAD.encode(), b"", b"", payload]) as command:
            self.assertEqual(exact_head_paths(base=BASE, head=HEAD),
                             ("backend/core/dragon_crawler.py", "deleted/file.py"))
            self.assertEqual(command.call_count, 4)
            self.assertEqual(command.call_args.args[0:4],
                             ("git", "diff", "--name-only", "--no-renames"))
            self.assertEqual(command.call_args.args[-3:], (BASE, HEAD, "--"))

    def test_truncated_nul_inventory_fails_closed(self) -> None:
        with patch("scripts.check_dragon_workflow_scope._run",
                   side_effect=[HEAD.encode(), b"", b"", b"missing/terminator"]):
            decision, _ = decide(base=BASE, head=HEAD)
            self.assertTrue(all(decision.values()))

    def test_bounded_stdout_memory_is_enforced(self) -> None:
        fake = subprocess.CompletedProcess(["git"], 0, b"x" * (MAX_DIFF_BYTES + 1), b"")
        with patch("scripts.check_dragon_workflow_scope.subprocess.run", return_value=fake):
            with self.assertRaises(OverflowError):
                _run("git", "diff")

    def test_receipt_only_written_from_an_actual_pr_event(self) -> None:
        with TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            context = {"GITHUB_OUTPUT": str(output),
                       "DRAGON_BASE_SHA": BASE,
                       "DRAGON_HEAD_SHA": HEAD,
                       "GITHUB_EVENT_NAME": "push"}
            with patch.dict(os.environ, context, clear=True):
                self.assertEqual(main(), 2)
                self.assertFalse(output.exists())
            context["GITHUB_EVENT_NAME"] = "pull_request"
            with patch.dict(os.environ, context, clear=True), patch(
                "scripts.check_dragon_workflow_scope.exact_head_paths",
                return_value=("frontend/src/product/crawlerClient.ts",),
            ):
                self.assertEqual(main(), 0)
            self.assertEqual(output.read_text(encoding="utf-8"),
                             "backend=false\nsource=false\nfrontend=true\n")

    def test_20_workflow_budget_is_not_relaxed(self) -> None:
        self.assertEqual(audit(ROOT), [])
        source = (ROOT / "scripts/check_ci_workflow_tiers.py").read_text(encoding="utf-8")
        self.assertIn("if automatic > 20:", source)

    def test_reusable_workflows_have_read_only_permissions_and_exact_checkout(self) -> None:
        quality = (WORKFLOWS / "backend-quality.yml").read_text(encoding="utf-8")
        for filename, job in (
            ("dragon-atlas-backend-bridge.yml", "dragon_backend:"),
            ("dragon-campaign-source-tests.yml", "dragon_source:"),
            ("dragon-campaign-frontend-checks.yml", "dragon_frontend:"),
        ):
            child = (WORKFLOWS / filename).read_text(encoding="utf-8")
            self.assertIn("  workflow_call:", child)
            self.assertNotIn("  pull_request:", child)
            self.assertIn("  workflow_dispatch:", child)
            self.assertIn("  contents: read", child)
            self.assertIn("ref: " + "$" + "{{ github.event.pull_request.head.sha || github.sha }}", child)
            self.assertIn(f"uses: ./.github/workflows/{filename}", quality)
            self.assertIn(job, quality)
        self.assertIn("python scripts/check_dragon_workflow_scope.py", quality)
        self.assertIn("github.event.pull_request.base.sha", quality)
        self.assertIn("github.event.pull_request.head.sha", quality)
        self.assertIn("persist-credentials: false", quality)
        self.assertIn("    permissions:\n      contents: read", quality)


if __name__ == "__main__":
    unittest.main()
