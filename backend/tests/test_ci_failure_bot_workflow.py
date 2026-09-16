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
