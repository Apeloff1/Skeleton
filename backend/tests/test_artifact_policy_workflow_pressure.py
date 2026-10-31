from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "artifact-policy.yml"


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_non_pr_artifact_policy_runs_are_never_cancelled() -> None:
    text = _workflow_text()

    # Per-PR superseded heads coalesce; manual and scheduled full scans stay
    # independently queued and are never cancelled. No duplicate push scan.
    assert "group: artifact-policy-${{ github.event_name }}-${{ github.event.pull_request.number || github.ref }}" in text
    assert "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in text
    assert "workflow_dispatch:" in text
    assert "schedule:" in text
    assert "pull_request:" in text


def test_main_push_artifact_policy_binds_event_before_commit() -> None:
    text = _workflow_text()

    assert "ARTIFACT_BASE: ${{ github.event.pull_request.base.sha || github.event.before }}" in text
    assert 'python scripts/check_artifact_policy.py --base "$ARTIFACT_BASE"' in text
    assert "python scripts/check_artifact_policy.py --all" in text
