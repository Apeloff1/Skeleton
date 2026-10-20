from __future__ import annotations

from pathlib import Path


def _workflow_text() -> str:
    root = Path(__file__).resolve().parents[2]
    return (root / ".github/workflows/queue-drain.yml").read_text(encoding="utf-8")


def test_queue_drain_does_not_self_thrash_on_main_pushes() -> None:
    workflow = _workflow_text()

    assert "workflow_dispatch:" in workflow
    assert "schedule:" in workflow
    # Recovery is hourly, rather than fanning out from each completed check.
    assert 'cron: "7 * * * *"' in workflow
    assert "workflow_run:" not in workflow
    assert 'workflows: ["Merge Readiness", "Prune redundant branches safely"]' not in workflow
    assert "branches: [main]" in workflow
    assert "\n  push:\n    branches: [main]\n    paths: ['.github/workflows/queue-drain.yml']" in workflow
    assert "group: queue-drain-v6-${{ github.repository }}" in workflow
    assert "cancel-in-progress: false" in workflow


def test_queue_drain_keeps_recovery_safety_boundary() -> None:
    workflow = _workflow_text()

    assert "runs-on: ubuntu-24.04-arm" in workflow
    assert "actions: write" in workflow
    assert "contents: read" in workflow
    assert "permissions: {}" in workflow
    assert "control_plane_paths = frozenset" in workflow
    assert "'.github/workflows/queue-drain.yml'" in workflow
    assert "'.github/workflows/pr-obsolete-run-drain.yml'" in workflow
    assert "github.event.workflow_run.conclusion == 'success'" not in workflow
    # The active drainer has a trusted schedule, manual dispatch and
    # default-branch change trigger. No untrusted workflow_run event may grant
    # the actions:write cancellation scope.
    assert "\n  workflow_run:\n" not in workflow
    assert "  schedule:" in workflow
    assert "  workflow_dispatch:" in workflow
    assert "branches: [main]" in workflow


def test_queue_drain_wake_is_low_frequency_canonical_validation() -> None:
    workflow = _workflow_text()

    assert 'cron: "7 * * * *"' in workflow
    assert "workflow_run:" not in workflow
    assert 'workflows: ["Drain obsolete PR Actions"]' not in workflow
    assert "branches: [main]" in workflow


def test_queue_drain_recovery_does_not_require_upstream_success() -> None:
    workflow = _workflow_text()

    # Scheduled recovery does not depend on any upstream workflow conclusion.
    assert 'cron: "7 * * * *"' in workflow
    assert "workflow_run:" not in workflow
    assert "github.event.workflow_run.conclusion == 'success'" not in workflow
    assert "github.event.workflow_run.conclusion != 'cancelled'" not in workflow
    assert "github.event.workflow_run.conclusion != 'skipped'" not in workflow


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
    assert "def cancel(run_id, security_lane=False):" in workflow
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


def test_queue_drain_has_one_recovery_worker_and_independent_housekeeping() -> None:
    workflow = _workflow_text()
    housekeeping = (
        Path(__file__).resolve().parents[2]
        / ".github/workflows/actions-housekeeping-cli.yml"
    ).read_text(encoding="utf-8")

    assert "  drain:\n" in workflow
    assert "  wake-housekeeping:\n" not in workflow
    assert "runs-on: ubuntu-24.04-arm" in workflow
    assert "gh workflow run actions-housekeeping-cli.yml" not in workflow
    assert "schedule:" in housekeeping
    assert "cron: '23 4,16 * * *'" in housekeeping
    assert "def recover_pr_numbers()" not in workflow


def test_queue_drain_reclaims_only_closed_pr_ghas_ai_runs() -> None:
    workflow = _workflow_text()

    assert "def closed_dynamic_ai_pr_run(run):" in workflow
    assert "dynamic/agents/github-advanced-security" in workflow
    assert "prefix = 'Code scanning AI findings on PR #'" in workflow
    assert "status, payload = request(f'/repos/{repo}/pulls/{number}')" in workflow
    assert "closed_dynamic_ai_cache" not in workflow
    assert "state = str(payload.get('state') or '')" in workflow
    assert "and head_repo == repo" in workflow
    assert "and head_ref == branch" in workflow
    assert "closed_dynamic_ai_queued" in workflow
    assert "closed_dynamic_ai_active" in workflow

    helper = workflow[
        workflow.index("def closed_dynamic_ai_pr_run"):
        workflow.index("def path(run):")
    ]
    assert "run_repo != repo" in helper
    assert "branch == 'main'" in helper
    assert "number_text.isdigit()" in helper
    assert "state = str(payload.get('state') or '')" in helper
    assert "and head_repo == repo" in helper
    assert "and head_ref == branch" in helper


def test_no_extra_housekeeping_dispatch_on_drain_events() -> None:
    workflow = _workflow_text()
    assert "  wake-housekeeping:" not in workflow
    assert "HOUSEKEEPING_WAKE_STALE_MINUTES" not in workflow
    assert "gh workflow run" not in workflow


def test_queue_drain_backpressure_stops_exhausted_mutation_sweeps() -> None:
    workflow = _workflow_text()

    assert "exc.code in {403, 429}" in workflow
    assert "'rate limit' in message" in workflow
    assert "if status not in retryable or status == 429:" in workflow
    assert "if status == 429:" in workflow
    assert "rate_limit_hit = True" in workflow
    assert "if rate_limit_hit or budget_exhausted:" in workflow
    assert "if pass_no < 4 and not rate_limit_hit and not budget_exhausted:" in workflow


def test_queue_drain_never_force_cancels_security_evidence() -> None:
    workflow = _workflow_text()

    assert "def security_lane(run):" in workflow
    assert "'github-advanced-security'" in workflow
    assert "if security_lane:" in workflow
    assert "status = cancel(run_id, security_lane=security_lane(run))" in workflow
    cancel = workflow[
        workflow.index("def cancel(run_id, security_lane=False):"):
        workflow.index("def main_sha():")
    ]
    assert cancel.index("if security_lane:") < cancel.index("/force-cancel")


def test_periodic_controller_coalescing_keeps_newest_live_wake() -> None:
    workflow = _workflow_text()
    assert "def periodic_controller_key(run):" in workflow
    assert "latest_controllers = {}" in workflow
    assert "int(latest['id']) > run_id" in workflow
    assert "coalesced_control_plane_queued" in workflow
    assert "event == 'workflow_run'" in workflow
    assert "event == 'schedule'" in workflow
    assert "'.github/workflows/repair-intake.yml'" in workflow
    assert "'pending', 'waiting'" in workflow


def test_drain_recovery_arm_lane_keeps_control_plane_safeguards() -> None:
    workflow = _workflow_text()
    drain = workflow[workflow.index("  drain:\n"):]
    assert "runs-on: ubuntu-24.04-arm" in drain
    assert "cancel-in-progress: false" in workflow
    assert "if stale_pr_run(run, open_pr_heads):" in drain
    assert "if security_lane:" in drain
    assert "if status == 429:" in drain
