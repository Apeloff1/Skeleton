from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TRAFFIC = ROOT / ".github" / "workflows" / "automation-traffic-manager.yml"
SUPERVISOR = ROOT / ".github" / "workflows" / "supervisor.yml"
SECRETARY = ROOT / ".github" / "workflows" / "secretary.yml"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _job_block(source: str, job: str, next_job: str | None = None) -> str:
    marker = f"  {job}:\n"
    start = source.index(marker)
    if next_job is None:
        return source[start:]
    end = source.index(f"  {next_job}:\n", start + len(marker))
    return source[start:end]


def test_traffic_manager_is_only_routine_schedule_for_supervisor_chain() -> None:
    traffic = _source(TRAFFIC)
    supervisor = _source(SUPERVISOR)
    secretary = _source(SECRETARY)

    assert 'cron: "*/10 * * * *"' in traffic
    assert "  schedule:" in traffic.split("permissions:", 1)[0]
    assert "  schedule:" not in supervisor.split("concurrency:", 1)[0]
    assert "  schedule:" not in secretary.split("concurrency:", 1)[0]


def test_traffic_manager_coalesces_overlapping_runs_without_cancelling_mutation() -> None:
    source = _source(TRAFFIC)
    concurrency = source.split("concurrency:\n", 1)[1].split("\n\njobs:", 1)[0]
    assert "group: automation-traffic-manager-${{ github.repository }}" in concurrency
    assert "cancel-in-progress: false" in concurrency


def test_traffic_control_uses_independent_arm_recovery_lane() -> None:
    source = _source(TRAFFIC)
    admission = _job_block(source, "admission", "relief")
    relief = _job_block(source, "relief", "dispatch")
    dispatch = _job_block(source, "dispatch")
    assert "runs-on: ubuntu-24.04-arm" in admission
    assert "runs-on: ubuntu-24.04-arm" in relief
    assert "runs-on: ubuntu-24.04-arm" in dispatch
    assert "runs-on: ubuntu-latest" not in admission
    assert "runs-on: ubuntu-latest" not in relief


def test_admission_job_is_read_only() -> None:
    source = _source(TRAFFIC)
    admission = _job_block(source, "admission", "relief")
    permissions = admission.split("    permissions:\n", 1)[1].split(
        "    runs-on:", 1
    )[0]
    assert "actions: read" in permissions
    assert "contents: read" in permissions
    assert "issues: read" in permissions
    assert "pull-requests: read" in permissions
    assert "write" not in permissions


def test_manager_invokes_fixed_admission_module() -> None:
    source = _source(TRAFFIC)
    assert "python -m skeleton.automation.traffic_manager" in source
    assert "eval " not in source
    assert "bash -c" not in source
    assert "sh -c" not in source


def test_manual_force_crosses_shell_boundary_only_through_env() -> None:
    source = _source(TRAFFIC)
    assert "TRAFFIC_FORCE:" in source
    admission = _job_block(source, "admission", "relief")
    run_block = admission.split(
        "- name: Evaluate bounded automation pressure", 1
    )[1]
    assert "${{ inputs.force" not in run_block
    assert "${{ github.event" not in run_block


def test_traffic_manager_dispatches_relief_only_on_pressure() -> None:
    source = _source(TRAFFIC)
    before_jobs = source.split("jobs:\n", 1)[0]
    assert "permissions: {}" in before_jobs

    relief = _job_block(source, "relief", "dispatch")
    assert "needs: admission" in relief
    assert "needs.admission.outputs.relieve == 'true'" in relief
    assert "actions: write" in relief
    assert "contents: read" in relief
    assert "pull-requests: write" in relief
    assert "gh workflow run queue-drain.yml" in relief
    assert "actions/workflows/queue-drain.yml/runs" in relief
    assert "requested waiting pending queued in_progress" in relief
    assert '--ref "$TRAFFIC_DEFAULT_BRANCH"' in relief


def test_relief_quenches_only_bounded_same_repo_main_prs() -> None:
    source = _source(TRAFFIC)
    relief = _job_block(source, "relief", "dispatch")
    assert "Quench non-exempt ready PR fanout" in relief
    assert "TRAFFIC_MAX_DRAFTS: '20'" in relief
    assert '.base.ref == "main"' in relief
    assert ".head.repo.full_name == $repo" in relief
    assert 'gh pr ready "$pr_number" --undo' in relief
    assert '--argjson max_drafts "$TRAFFIC_MAX_DRAFTS"' in relief
    assert "][: $max_drafts][]" in relief
    assert "TRAFFIC_MAX_DRAFTS <= 100" in relief


def test_relief_preserves_in_progress_current_head_validation() -> None:
    source = _source(TRAFFIC)
    relief = _job_block(source, "relief", "dispatch")

    assert "actions/runs?status=in_progress&per_page=100" in relief
    assert "gh api --paginate --slurp" in relief
    assert 'select(type == "string" and test("^[0-9a-fA-F]{40}$"))' in relief
    assert '--slurpfile active_heads "$active_heads"' in relief
    assert '.head.sha as $head_sha' in relief
    assert 'index($head_sha)) == null' in relief
    assert "In-progress current-head validations are preserved" in relief


def test_relief_preserves_explicit_priority_labels() -> None:
    source = _source(TRAFFIC)
    relief = _job_block(source, "relief", "dispatch")
    assert '"traffic:keep-ready"' in relief
    assert '"ci:priority"' in relief
    assert '"queue:exempt"' in relief
    assert "A concurrent actor may have drafted it first" in relief


def test_traffic_manager_exposes_relief_observability() -> None:
    source = _source(TRAFFIC)
    admission = _job_block(source, "admission", "relief")
    assert "stale_queued_runs:" in admission
    assert "provider_tombstones:" in admission
    assert "oldest_queued_age_seconds:" in admission
    assert "inventory_saturated:" in admission
    assert "relieve:" in admission
    assert "relief_reason:" in admission


def test_traffic_manager_dispatches_supervisor_only_after_admission() -> None:
    source = _source(TRAFFIC)
    dispatch = _job_block(source, "dispatch")
    assert "needs: admission" in dispatch
    assert "needs.admission.outputs.admit == 'true'" in dispatch
    assert "actions: write" in dispatch
    assert "contents: read" in dispatch
    assert "pull-requests: write" not in dispatch
    assert "gh workflow run supervisor.yml" in dispatch
    assert '--ref "$TRAFFIC_DEFAULT_BRANCH"' in dispatch


def test_dispatch_is_bound_to_exact_admitted_default_branch_head() -> None:
    source = _source(TRAFFIC)
    admission = _job_block(source, "admission", "relief")
    dispatch = _job_block(source, "dispatch")

    assert "admitted_base_sha: ${{ steps.identity.outputs.base_sha }}" in admission
    assert "name: Capture immutable admission identity" in admission
    assert '[[ "$GITHUB_SHA" =~ ^[0-9a-f]{40}$ ]]' in admission
    assert 'echo "base_sha=$GITHUB_SHA" >> "$GITHUB_OUTPUT"' in admission

    assert (
        "TRAFFIC_ADMITTED_BASE_SHA: "
        "${{ needs.admission.outputs.admitted_base_sha }}"
    ) in dispatch
    assert "Revalidate admission and dispatch reviewed supervisor workflow" in dispatch
    assert "/git/ref/heads/${TRAFFIC_DEFAULT_BRANCH}" in dispatch
    assert '[[ "$TRAFFIC_ADMITTED_BASE_SHA" =~ ^[0-9a-f]{40}$ ]]' in dispatch
    assert '[[ "$live_sha" != "$TRAFFIC_ADMITTED_BASE_SHA" ]]' in dispatch
    assert "gh workflow run supervisor.yml" in dispatch


def test_stale_admission_cannot_fall_through_to_separate_dispatch_step() -> None:
    source = _source(TRAFFIC)
    dispatch = _job_block(source, "dispatch")
    assert dispatch.count("gh workflow run supervisor.yml") == 1
    assert dispatch.count("name: Revalidate admission and dispatch reviewed supervisor workflow") == 1
    assert "name: Dispatch reviewed supervisor workflow" not in dispatch
    guard_position = dispatch.index('[[ "$live_sha" != "$TRAFFIC_ADMITTED_BASE_SHA" ]]')
    exit_position = dispatch.index("exit 0", guard_position)
    dispatch_position = dispatch.index("gh workflow run supervisor.yml", exit_position)
    assert guard_position < exit_position < dispatch_position


def test_stale_dispatch_guard_does_not_interpolate_expressions_into_shell() -> None:
    source = _source(TRAFFIC)
    dispatch = _job_block(source, "dispatch")
    run_block = dispatch.split(
        "- name: Revalidate admission and dispatch reviewed supervisor workflow", 1
    )[1]
    assert "${{ " not in run_block
    assert "$TRAFFIC_ADMITTED_BASE_SHA" in run_block
    assert "${TRAFFIC_DEFAULT_BRANCH}" in run_block
    assert "$GITHUB_REPOSITORY" in run_block


def test_dispatch_validates_provider_head_before_comparison() -> None:
    source = _source(TRAFFIC)
    dispatch = _job_block(source, "dispatch")
    assert '[[ "$live_sha" =~ ^[0-9a-f]{40}$ ]]' in dispatch
    assert "GitHub returned an invalid default-branch head" in dispatch
    assert '[[ "$TRAFFIC_DEFAULT_BRANCH" =~ ^[A-Za-z0-9._/-]+$ ]]' in dispatch


def test_supervisor_exposes_reusable_entrypoint_and_no_schedule() -> None:
    source = _source(SUPERVISOR)
    trigger = source.split("concurrency:", 1)[0]
    assert "  workflow_call:" in trigger
    assert "  workflow_dispatch:" in trigger
    assert "  schedule:" not in trigger


def test_secretary_has_no_routine_schedule() -> None:
    source = _source(SECRETARY)
    trigger = source.split("concurrency:", 1)[0]
    assert "  workflow_dispatch:" in trigger
    assert "  schedule:" not in trigger


def test_traffic_manager_uses_pinned_reviewed_actions() -> None:
    source = _source(TRAFFIC)
    assert (
        "actions/checkout@"
        "3d3c42e5aac5ba805825da76410c181273ba90b1"
    ) in source
    assert (
        "actions/setup-python@"
        "5fda3b95a4ea91299a34e894583c3862153e4b97"
    ) in source
    assert "@main" not in source
    assert "@master" not in source
