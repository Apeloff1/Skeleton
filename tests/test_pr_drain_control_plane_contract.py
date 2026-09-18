from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QUEUE_DRAIN = ROOT / ".github" / "workflows" / "queue-drain.yml"
PR_DRAIN = ROOT / ".github" / "workflows" / "pr-obsolete-run-drain.yml"


def test_global_queue_drain_preserves_pr_cleanup_control_plane() -> None:
    text = QUEUE_DRAIN.read_text(encoding="utf-8")

    assert "'.github/workflows/pr-obsolete-run-drain.yml'" in text
    assert "`pr-obsolete-run-drain.yml`" in text


def test_pr_backlog_sweeps_are_non_preemptive_and_globally_coalesced() -> None:
    text = PR_DRAIN.read_text(encoding="utf-8")

    assert "group: pr-run-drain-${{ github.repository }}" in text
    assert "cancel-in-progress: false" in text
    assert "cancel-in-progress: true" not in text
    assert "github.event_name == 'schedule' || github.event_name == 'push'" in text


def test_event_wakeups_use_the_global_conservative_sweep() -> None:
    text = PR_DRAIN.read_text(encoding="utf-8")

    assert "github.event.workflow_run.head_branch" in text
    assert "github.event.workflow_run.head_sha" in text
    assert "github.event.workflow_run.head_repository.full_name == github.repository" in text
    assert "github.event.workflow_run.head_branch != github.event.repository.default_branch" in text
    assert 'branches:\n      - "*"\n      - "**"' in text
    assert text.count("python backend/scripts/pr_obsolete_run_sweep.py") == 2
    assert "python backend/scripts/pr_obsolete_run_from_workflow_run.py" not in text
    assert text.count("MAX_CANCELLATIONS: '250'") == 2


def test_pr_drain_recovery_uses_general_runner_capacity() -> None:
    text = PR_DRAIN.read_text(encoding="utf-8")

    assert text.count("runs-on: ubuntu-latest") == 2
    assert "runs-on: ubuntu-24.04-arm" not in text
