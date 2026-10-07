from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "supervisor.yml"


def _source() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _job_block(source: str, job: str, next_job: str | None = None) -> str:
    marker = f"  {job}:\n"
    start = source.index(marker)
    if next_job is None:
        return source[start:]
    end_marker = f"  {next_job}:\n"
    end = source.index(end_marker, start + len(marker))
    return source[start:end]


def test_supervisor_workflow_has_no_workflow_wide_authority() -> None:
    source = _source()
    before_jobs = source.split("jobs:\n", 1)[0]
    assert "permissions: {}" in before_jobs
    assert "write-all" not in source
    assert "read-all" not in source


def test_supervisor_workflow_is_reusable_and_manual_only() -> None:
    source = _source()
    trigger = source.split("concurrency:\n", 1)[0]
    assert "  workflow_call:" in trigger
    assert "  workflow_dispatch:" in trigger
    assert "  schedule:" not in trigger
    assert "pull_request:" not in trigger
    assert "push:" not in trigger
    assert "workflow_run:" not in trigger


def test_supervisor_serializes_repository_runs_without_mid_mutation_cancel() -> None:
    source = _source()
    concurrency = source.split("concurrency:\n", 1)[1].split("\n\n", 1)[0]
    assert "group: repository-supervisor-${{ github.repository }}" in concurrency
    assert "cancel-in-progress: false" in concurrency


def test_execution_identity_is_bound_at_workflow_scope() -> None:
    source = _source()
    required = (
        "GITHUB_REPOSITORY: ${{ github.repository }}",
        "SUPERVISOR_BASE_SHA: ${{ github.sha }}",
        "SUPERVISOR_DEFAULT_BRANCH: ${{ github.event.repository.default_branch }}",
        "SUPERVISOR_RUN_ID: ${{ github.run_id }}",
        "SUPERVISOR_RUN_ATTEMPT: ${{ github.run_attempt }}",
    )
    for fragment in required:
        assert fragment in source


def test_plan_checks_out_exact_execution_sha_without_persisted_credentials() -> None:
    source = _source()
    plan = _job_block(source, "plan", "secretary")
    assert "name: Checkout immutable execution commit" in plan
    assert "ref: ${{ github.sha }}" in plan
    assert "persist-credentials: false" in plan
    assert "ref: ${{ github.event.repository.default_branch }}" not in plan


def test_secretary_checks_out_same_exact_execution_sha() -> None:
    source = _source()
    secretary = _job_block(source, "secretary")
    assert "name: Checkout immutable admitted commit" in secretary
    assert "ref: ${{ github.sha }}" in secretary
    assert "persist-credentials: false" in secretary
    assert "ref: ${{ github.event.repository.default_branch }}" not in secretary


def test_both_jobs_use_exactly_two_immutable_checkouts() -> None:
    source = _source()
    assert source.count("ref: ${{ github.sha }}") == 2
    assert source.count("persist-credentials: false") == 2


def test_plan_is_read_only() -> None:
    source = _source()
    plan = _job_block(source, "plan", "secretary")
    permissions = plan.split("    permissions:\n", 1)[1].split("    runs-on:", 1)[0]
    assert "actions: read" in permissions
    assert "contents: read" in permissions
    assert "issues: read" in permissions
    assert "pull-requests: read" in permissions
    assert "write" not in permissions


def test_secretary_has_only_content_and_pull_request_write_authority() -> None:
    source = _source()
    secretary = _job_block(source, "secretary")
    permissions = secretary.split("    permissions:\n", 1)[1].split("    runs-on:", 1)[0]
    assert "contents: write" in permissions
    assert "issues: read" in permissions
    assert "pull-requests: write" in permissions
    for forbidden in (
        "actions: write",
        "checks: write",
        "issues: write",
        "packages: write",
        "security-events: write",
        "statuses: write",
        "workflows: write",
        "id-token: write",
    ):
        assert forbidden not in permissions


def test_manual_dispatch_must_still_target_default_branch() -> None:
    source = _source()
    plan = _job_block(source, "plan", "secretary")
    assert "SUPERVISOR_EVENT_REF: ${{ github.ref }}" in plan
    assert (
        "SUPERVISOR_EXPECTED_REF: refs/heads/"
        "${{ github.event.repository.default_branch }}"
    ) in plan
    assert 'test "$SUPERVISOR_EVENT_REF" = "$SUPERVISOR_EXPECTED_REF"' in plan


def test_default_branch_guard_crosses_shell_boundary_through_env() -> None:
    source = _source()
    plan = _job_block(source, "plan", "secretary")
    guard = plan.split(
        "- name: Require default-branch execution", 1
    )[1].split(
        "- name: Checkout immutable execution commit", 1
    )[0]
    assert "${{ github." not in guard
    assert "$SUPERVISOR_EVENT_REF" in guard
    assert "$SUPERVISOR_EXPECTED_REF" in guard


def test_plan_exports_cross_job_execution_proof() -> None:
    source = _source()
    plan = _job_block(source, "plan", "secretary")
    required = (
        "delegation_b64: ${{ steps.supervisor.outputs.delegation_b64 }}",
        "snapshot_fingerprint: ${{ steps.supervisor.outputs.snapshot_fingerprint }}",
        "execution_fingerprint: ${{ steps.supervisor.outputs.execution_fingerprint }}",
        "base_sha: ${{ steps.supervisor.outputs.base_sha }}",
    )
    for fragment in required:
        assert fragment in plan


def test_secretary_requires_plan_base_to_equal_current_run_sha() -> None:
    source = _source()
    secretary = _job_block(source, "secretary")
    assert "needs.plan.outputs.base_sha == github.sha" in secretary
    assert "needs.plan.outputs.delegation_b64 != ''" in secretary


def test_secretary_receives_execution_fingerprint_as_data() -> None:
    source = _source()
    secretary = _job_block(source, "secretary")
    assert (
        "SUPERVISOR_EXECUTION_FINGERPRINT: "
        "${{ needs.plan.outputs.execution_fingerprint }}"
    ) in secretary
    assert (
        "SUPERVISOR_SNAPSHOT_FINGERPRINT: "
        "${{ needs.plan.outputs.snapshot_fingerprint }}"
    ) in secretary


def test_model_secret_is_never_interpolated_into_run_shell() -> None:
    source = _source()
    assert "MODEL_API_KEY: ${{ secrets.MODEL_API_KEY }}" in source
    for line in source.splitlines():
        if "run:" in line:
            assert "secrets.MODEL_API_KEY" not in line


def test_supervisor_entrypoints_are_fixed_module_invocations() -> None:
    source = _source()
    assert "python -m skeleton.automation.supervisor" in source
    assert "python -m skeleton.automation.secretary" in source
    assert "eval " not in source
    assert "bash -c" not in source
    assert "sh -c" not in source


def test_supervisor_workflow_uses_pinned_reviewed_actions() -> None:
    source = _source()
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


def test_secretary_timeout_keeps_a_bounded_execution_window() -> None:
    source = _source()
    secretary = _job_block(source, "secretary")
    assert "timeout-minutes: 45" in secretary

def test_worker_health_surface_is_tracked_by_workflow_security() -> None:
    workflow = ROOT / ".github" / "workflows" / "workflow-input-security.yml"
    source = workflow.read_text(encoding="utf-8")
    required = (
        "skeleton/automation/worker_health.py",
        "tests/test_worker_health.py",
        "skeleton/testing/test_bot_manager.py",
    )
    for fragment in required:
        assert source.count(fragment) == 2


def test_merge_readiness_runs_worker_health_regressions() -> None:
    workflow = ROOT / ".github" / "workflows" / "merge-readiness.yml"
    source = workflow.read_text(encoding="utf-8")
    required = (
        "tests/test_worker_health.py",
        "skeleton/testing/test_bot_manager.py",
    )
    for fragment in required:
        assert fragment in source

def test_builder_plane_surface_is_tracked_by_workflow_security() -> None:
    workflow = ROOT / ".github" / "workflows" / "workflow-input-security.yml"
    source = workflow.read_text(encoding="utf-8")
    required = (
        "skeleton/automation/builder_plane.py",
        "tests/test_builder_plane.py",
        "tests/test_builder_plane_integration.py",
    )
    for fragment in required:
        assert source.count(fragment) == 2


def test_merge_readiness_runs_builder_plane_regressions() -> None:
    workflow = ROOT / ".github" / "workflows" / "merge-readiness.yml"
    source = workflow.read_text(encoding="utf-8")
    required = (
        "tests/test_builder_plane.py",
        "tests/test_builder_plane_integration.py",
    )
    for fragment in required:
        assert fragment in source
