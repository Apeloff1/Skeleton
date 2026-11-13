from __future__ import annotations

from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "automerge-control-plane.yml"
SCRIPT = REPO_ROOT / "skeleton" / "automation" / "dependabot_merge_policy.py"


def test_automerge_worker_uses_trusted_default_branch_and_exact_head_gates() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "ref: ${{ github.event.repository.default_branch }}" in text
    assert "persist-credentials: false" in text
    assert "github.event.workflow_run.head_repository.full_name == github.repository" in text
    assert "github.event.workflow_run.event == 'pull_request'" in text
    assert "github.event.workflow_run.conclusion == 'success'" in text
    assert "python -m skeleton.pr_automation.automerge_cli" in text
    assert "python skeleton/automation/dependabot_merge_policy.py" not in text
    assert "python -m skeleton.automation.dependabot_merge_policy" not in text


def test_dependabot_policy_starts_without_project_dependencies() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=REPO_ROOT,
        env={},
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "--repo" in completed.stdout
    assert "ModuleNotFoundError" not in completed.stderr
