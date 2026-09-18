from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "artifact-policy.yml"


def test_artifact_policy_main_runs_are_full_scan_and_ref_coalesced() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "group: artifact-policy-${{ github.event.pull_request.number || github.ref }}" in text
    assert "cancel-in-progress: true" in text
    assert "ARTIFACT_BASE: ${{ github.event.pull_request.base.sha }}" in text
    assert "github.event.before" not in text


def test_artifact_policy_pr_runs_remain_incremental() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert 'python scripts/check_artifact_policy.py --base "$ARTIFACT_BASE"' in text
    assert "python scripts/check_artifact_policy.py --all" in text
