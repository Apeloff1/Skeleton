from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QUEUE_DRAIN = ROOT / ".github" / "workflows" / "queue-drain.yml"
PR_DRAIN = ROOT / ".github" / "workflows" / "pr-obsolete-run-drain.yml"


def test_global_queue_drain_preserves_pr_cleanup_control_plane() -> None:
    text = QUEUE_DRAIN.read_text(encoding="utf-8")

    assert "'.github/workflows/pr-obsolete-run-drain.yml'" in text
    assert "`pr-obsolete-run-drain.yml`" in text


def test_pr_backlog_sweeps_are_non_preemptive() -> None:
    text = PR_DRAIN.read_text(encoding="utf-8")

    assert "cancel-in-progress: ${{ github.event_name == 'workflow_run' }}" in text
    assert "cancel-in-progress: true" not in text
    assert "github.event_name == 'schedule' || github.event_name == 'push'" in text


def test_event_drains_remain_scoped_per_pr_branch() -> None:
    text = PR_DRAIN.read_text(encoding="utf-8")

    assert "github.event.workflow_run.head_branch" in text
    assert "github.event.workflow_run.head_sha" in text
    assert "github.event.workflow_run.head_repository.full_name == github.repository" in text
    assert "github.event.workflow_run.head_branch != github.event.repository.default_branch" in text
    assert 'branches:\n      - "*"\n      - "**"' in text
    assert "toJSON(github.event.workflow_run.pull_requests.*.number)" in text
    assert "WORKFLOW_RUN_PR_HINTS" in text
    assert "pull_requests[0]" not in text


def test_pr_drain_recovery_uses_general_runner_capacity() -> None:
    text = PR_DRAIN.read_text(encoding="utf-8")

    assert text.count("runs-on: ubuntu-latest") == 2
    assert "runs-on: ubuntu-24.04-arm" not in text
