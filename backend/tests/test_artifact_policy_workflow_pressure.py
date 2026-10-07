from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "artifact-policy.yml"


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_non_pr_artifact_policy_runs_keep_per_generation_identity() -> None:
    text = _workflow_text()

    assert "group: artifact-policy-${{ github.event.pull_request.number || github.sha }}" in text
    assert "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in text
    assert "github.ref }}" not in text.split("permissions:", 1)[0]


def test_main_push_artifact_policy_binds_event_before_commit() -> None:
    text = _workflow_text()

    assert "ARTIFACT_BASE: ${{ github.event.pull_request.base.sha || github.event.before }}" in text
    assert 'python scripts/check_artifact_policy.py --base "$ARTIFACT_BASE"' in text
    assert "python scripts/check_artifact_policy.py --all" in text
