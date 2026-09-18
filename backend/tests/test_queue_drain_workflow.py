from __future__ import annotations

from pathlib import Path


def _workflow_text() -> str:
    root = Path(__file__).resolve().parents[2]
    return (root / ".github/workflows/queue-drain.yml").read_text(encoding="utf-8")


def test_queue_drain_does_not_self_thrash_on_main_pushes() -> None:
    workflow = _workflow_text()

    assert "workflow_dispatch:" in workflow
    assert "schedule:" in workflow
    assert 'cron: "2-57/5 * * * *"' in workflow
    assert "workflow_run:" in workflow
    assert 'workflows: ["Merge Readiness"]' in workflow
    assert "types: [completed]" in workflow
    assert "branches: [main]" in workflow
    assert "\n  push:\n    branches: [main]\n    paths: ['.github/workflows/queue-drain.yml']" in workflow
    assert "cancel-in-progress: false" in workflow


def test_queue_drain_keeps_recovery_safety_boundary() -> None:
    workflow = _workflow_text()

    assert "runs-on: ubuntu-latest" in workflow
    assert "actions: write" in workflow
    assert "contents: read" in workflow
    assert "permissions: {}" in workflow
    assert "control_plane_paths = frozenset" in workflow
    assert "'.github/workflows/queue-drain.yml'" in workflow
    assert "'.github/workflows/pr-obsolete-run-drain.yml'" in workflow
    assert "github.event.workflow_run.conclusion == 'success'" not in workflow
    assert "github.event.workflow_run.head_repository.full_name == github.repository" in workflow
    assert "github.event.workflow_run.head_branch == github.event.repository.default_branch" in workflow


def test_queue_drain_wake_is_low_frequency_canonical_validation() -> None:
    workflow = _workflow_text()

    assert 'workflows: ["Merge Readiness"]' in workflow
    assert 'workflows: ["Drain obsolete PR Actions"]' not in workflow
    assert "branches: [main]" in workflow


def test_queue_drain_recovery_does_not_require_upstream_success() -> None:
    workflow = _workflow_text()

    assert "types: [completed]" in workflow
    assert "github.event.workflow_run.conclusion == 'success'" not in workflow
    assert "github.event.workflow_run.head_repository.full_name == github.repository" in workflow
    assert "github.event.workflow_run.head_branch == github.event.repository.default_branch" in workflow
    assert "Any trusted terminal main Merge Readiness completion may wake recovery." in workflow


def test_queue_drain_reclaims_obsolete_same_repository_pr_runs() -> None:
    workflow = _workflow_text()

    assert "def list_open_pr_heads():" in workflow
    assert "same-repository open PR has incomplete head identity" in workflow
    assert "def stale_pr_run(run, open_pr_heads):" in workflow
    assert "run.get('event') != 'pull_request'" in workflow
    assert "run_repo != repo or not branch or branch == 'main' or not sha" in workflow
    assert "sha not in open_pr_heads.get(branch, set())" in workflow
    assert "obsolete_pr_queued" in workflow
    assert "obsolete_pr_active" in workflow

    queued_guard = workflow.index("if stale_pr_run(run, open_pr_heads):")
    queued_control_plane = workflow.index("if is_control_plane(run):", queued_guard)
    assert queued_guard < queued_control_plane

    active_loop = workflow.index("for run in active:")
    active_guard = workflow.index("if stale_pr_run(run, open_pr_heads):", active_loop)
    active_control_plane = workflow.index("if is_control_plane(run):", active_guard)
    assert active_guard < active_control_plane
