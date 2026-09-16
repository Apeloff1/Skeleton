from __future__ import annotations

from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci-failure-bot.yml"
SCRIPT = REPO_ROOT / "skeleton" / "automation" / "ci_failure_bot.py"


def test_ci_failure_bot_bypasses_root_package_imports() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "run: python skeleton/automation/ci_failure_bot.py" in text
    assert "python -m skeleton.automation.ci_failure_bot" not in text


def test_ci_failure_bot_remains_read_only_and_uses_trusted_code() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "contents: read" in text
    assert "actions: read" in text
    assert "issues: write" not in text
    assert "pull-requests: write" not in text
    assert "contents: write" not in text
    assert "ref: ${{ github.event.repository.default_branch }}" in text
    assert "persist-credentials: false" in text
    assert "workflow_run.head_sha" not in text


def test_ci_failure_bot_script_starts_without_project_dependencies() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=REPO_ROOT,
        env={},
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    # Startup reaches the script's own required-environment guard instead of
    # failing while importing dependency-bearing skeleton package modules.
    assert completed.returncode != 0
    assert "GITHUB_REPOSITORY is required" in completed.stderr
    assert "ModuleNotFoundError" not in completed.stderr
