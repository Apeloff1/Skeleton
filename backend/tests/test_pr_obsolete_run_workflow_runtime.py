from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "backend" / "scripts" / "pr_obsolete_run_from_workflow_run.py"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pr-obsolete-run-drain.yml"


def test_workflow_run_adapter_is_directly_executable_from_repo_root() -> None:
    env = os.environ.copy()
    for key in (
        "GH_TOKEN",
        "REPO",
        "CURRENT_RUN_ID",
        "PR_NUMBER",
        "WORKFLOW_RUN_PR_HINTS",
        "EVENT_HEAD_REPO",
        "EVENT_HEAD_REF",
        "EVENT_HEAD_SHA",
        "DEFAULT_BRANCH",
    ):
        env.pop(key, None)

    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )

    assert result.returncode != 0
    assert "ModuleNotFoundError" not in result.stderr
    assert "GH_TOKEN" in result.stderr


def test_privileged_drainer_starts_when_lifecycle_signal_is_requested() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert 'workflows: ["PR Lifecycle Signal"]' in text
    assert "types: [requested]" in text
    assert "types: [completed]" not in text
    assert 'branches:\n      - "*"\n      - "**"' in text
    assert "group: pr-run-drain-${{ github.repository }}" in text
    assert "cancel-in-progress: false" in text
    assert text.count("python backend/scripts/pr_obsolete_run_sweep.py") == 2
    assert "python backend/scripts/pr_obsolete_run_from_workflow_run.py" not in text
