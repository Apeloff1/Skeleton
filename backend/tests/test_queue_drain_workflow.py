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
    assert "group: queue-drain-v3-${{ github.repository }}" in workflow
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


def test_queue_drain_reclaims_deleted_main_workflow_runs_only() -> None:
    workflow = _workflow_text()

    assert "def current_workflow_paths(head_sha):" in workflow
    assert "/contents/.github/workflows?{query}" in workflow
    assert "current workflow file inventory is empty" in workflow
    assert "def orphaned_main_workflow_run(run, current_paths):" in workflow
    assert "(run.get('head_branch') or '') == 'main'" in workflow
    assert "workflow_path.startswith('.github/workflows/')" in workflow
    assert "workflow_path not in current_paths" in workflow
    assert "orphaned_main_queued" in workflow
    assert "orphaned_main_active" in workflow

    # The helper is deliberately main-only: a PR may validly introduce a new
    # workflow file that does not exist on the current default branch.
    helper = workflow[
        workflow.index("def orphaned_main_workflow_run"):
        workflow.index("def list_open_pr_heads")
    ]
    assert "pull_request" not in helper
    assert "head_branch" in helper


def test_queue_drain_force_cancels_provider_stuck_obsolete_runs() -> None:
    workflow = _workflow_text()

    assert "def post_with_retry(path):" in workflow
    assert "def run_completed(run_id):" in workflow
    assert "def cancel(run_id):" in workflow
    assert "/actions/runs/{run_id}/force-cancel" in workflow
    assert "status in {409, 422} and run_completed(run_id)" in workflow
    assert "status in {409, 422} or status in retryable" in workflow
    assert "forced in {409, 422} and run_completed(run_id)" in workflow

    normal = workflow.index("f'/repos/{repo}/actions/runs/{run_id}/cancel'")
    force = workflow.index("f'/repos/{repo}/actions/runs/{run_id}/force-cancel'")
    assert normal < force


def test_queue_drain_reclaims_stale_dynamic_codeql_pr_runs() -> None:
    workflow = _workflow_text()

    assert "numbered_heads = {}" in workflow
    assert "numbered_heads[number] = sha" in workflow
    assert "return heads, numbered_heads" in workflow
    assert "def stale_dynamic_pr_run(run, open_pr_numbered_heads):" in workflow
    assert "run.get('event') != 'dynamic'" in workflow
    assert "dynamic/github-code-scanning/codeql" in workflow
    assert "prefix = 'refs/pull/'" in workflow
    assert "suffix = '/head'" in workflow
    assert "number_text.isdigit()" in workflow
    assert "sha != open_pr_numbered_heads.get(int(number_text), '')" in workflow
    assert "obsolete_dynamic_pr_queued" in workflow
    assert "obsolete_dynamic_pr_active" in workflow

    helper = workflow[
        workflow.index("def stale_dynamic_pr_run"):
        workflow.index("def path(run):")
    ]
    assert "run_repo != repo" in helper
    assert "refs/pull/" in helper
    assert "dynamic/github-code-scanning/codeql" in helper


def test_queue_drain_wakes_housekeeping_only_for_old_eligible_pr_backlog() -> None:
    workflow = _workflow_text()

    assert "Wake exact stale-PR housekeeping when needed" in workflow
    assert "HOUSEKEEPING_WORKFLOW: actions-housekeeping-cli.yml" in workflow
    assert "HOUSEKEEPING_WAKE_STALE_MINUTES: '1440'" in workflow
    assert 'actions/runs?status=queued&per_page=100&page=${page}' in workflow
    assert '[[ "$event" == \'pull_request\' ]] || continue' in workflow
    assert "*Malware*|*Secret*|*Security*|*CodeQL*|*Provenance*" in workflow
    assert "for page in $(seq 1 10)" in workflow
    assert "exceeded its bounded 1,000-run queued inventory scan" in workflow


def test_queue_drain_does_not_duplicate_live_housekeeping() -> None:
    workflow = _workflow_text()

    assert "for status_name in requested waiting pending queued in_progress; do" in workflow
    assert '/actions/workflows/${HOUSEKEEPING_WORKFLOW}/runs?status=${status_name}&per_page=1' in workflow
    assert "existing Housekeeping run is ${housekeeping_status}" in workflow
    assert 'gh workflow run "$HOUSEKEEPING_WORKFLOW" --repo "$REPO" --ref main' in workflow
    assert "Housekeeping independently re-proves PR/run identity before any cancellation." in workflow


def test_housekeeping_wake_is_independent_arm_job() -> None:
    workflow = _workflow_text()

    drain_start = workflow.index("  drain:\n")
    wake_start = workflow.index("  wake-housekeeping:\n")
    drain = workflow[drain_start:wake_start]
    wake = workflow[wake_start:]

    assert "Wake exact stale-PR housekeeping when needed" not in drain
    assert "runs-on: ubuntu-latest" in drain
    assert "Wake exact stale-PR housekeeping when needed" in wake
    assert "runs-on: ubuntu-24.04-arm" in wake
    assert "timeout-minutes: 3" in wake
    assert "actions: write" in wake
    assert "github.event.workflow_run.head_repository.full_name == github.repository" in wake
    assert "github.event.workflow_run.head_branch == github.event.repository.default_branch" in wake


def test_queue_drain_reclaims_only_closed_pr_ghas_ai_runs() -> None:
    workflow = _workflow_text()

    assert "def closed_dynamic_ai_pr_run(run):" in workflow
    assert "dynamic/agents/github-advanced-security" in workflow
    assert "prefix = 'Code scanning AI findings on PR #'" in workflow
    assert "status, payload = request(f'/repos/{repo}/pulls/{number}')" in workflow
    assert "closed_dynamic_ai_cache" not in workflow
    assert "str(payload.get('state') or '') == 'closed'" in workflow
    assert "head_repo == repo" in workflow
    assert "head_ref == branch" in workflow
    assert "closed_dynamic_ai_queued" in workflow
    assert "closed_dynamic_ai_active" in workflow

    helper = workflow[
        workflow.index("def closed_dynamic_ai_pr_run"):
        workflow.index("def path(run):")
    ]
    assert "run_repo != repo" in helper
    assert "branch == 'main'" in helper
    assert "number_text.isdigit()" in helper
