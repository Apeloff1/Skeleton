from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/pr-automation-index.yml"


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_privileged_workflow_uses_only_trusted_default_branch_triggers():
    text = _workflow()
    assert "workflow_run:" in text
    assert "schedule:" in text
    assert "workflow_dispatch:" in text
    assert "pull_request_target:" not in text
    assert "pull_request_review:" not in text
    assert "pull_request_review_comment:" not in text
    assert "ref: ${{ github.event.repository.default_branch }}" in text
    assert "persist-credentials: false" in text
    assert "github.event.pull_request.head" not in text
    assert "github.head_ref" not in text


def test_privileged_python_executes_only_staged_package_in_isolated_mode():
    text = _workflow()
    assert 'trusted_root="$RUNNER_TEMP/trusted-pr-automation"' in text
    assert 'cp -R skeleton/pr_automation "$trusted_root/pr_automation"' in text
    assert "python -I -c" in text
    assert "sys.path.insert(0, root)" in text
    assert "from pr_automation.runner import main" in text
    assert "python -m skeleton.pr_automation.runner" not in text


def test_workflow_reacts_only_to_terminal_ci_state_and_serializes_writers():
    text = _workflow()
    assert "types: [completed]" in text
    assert "types: [requested, in_progress, completed]" not in text
    assert "types: [requested]" not in text
    assert "types: [in_progress]" not in text
    assert "- Merge Readiness" in text
    assert "group: pr-automation-index" in text
    assert "cancel-in-progress: false" in text
    assert "branches-ignore:\n      - main" in text
    assert 'branches:\n      - "*"\n      - "**"' not in text


def test_workflow_resolves_all_branch_completions_from_head_identity():
    text = _workflow()
    assert "github.event.workflow_run.head_sha" in text
    assert "github.event.workflow_run.head_branch" in text
    assert "--head-sha" in text
    assert "--head-ref" in text
    assert "--pr-hints-json" in text
    assert "toJSON(github.event.workflow_run.pull_requests.*.number)" in text
    assert "pull_requests[0]" not in text
    assert 'pr="${INPUT_PR:-${WORKFLOW_RUN_PR:-}}"' not in text
    assert "workflow_run completion is missing head SHA or branch" in text


def test_workflow_defaults_are_fail_closed_and_bounded():
    text = _workflow()
    assert "PR_AUTOMATION_REQUIRED_CHECKS: ${{ vars.PR_AUTOMATION_REQUIRED_CHECKS || 'Merge Readiness' }}" in text
    assert "PR_AUTOMATION_REQUIRED_APPROVALS: ${{ vars.PR_AUTOMATION_REQUIRED_APPROVALS || '1' }}" in text
    assert "PR_AUTOMATION_REQUIRE_CHECKS: ${{ vars.PR_AUTOMATION_REQUIRE_CHECKS || 'true' }}" in text
    assert "PR_AUTOMATION_REQUIRE_NO_CHANGES_REQUESTED: ${{ vars.PR_AUTOMATION_REQUIRE_NO_CHANGES_REQUESTED || 'true' }}" in text
    assert "PR_AUTOMATION_REQUIRE_RESOLVED_THREADS: ${{ vars.PR_AUTOMATION_REQUIRE_RESOLVED_THREADS || 'true' }}" in text
    assert "PR_AUTOMATION_ALLOW_FORK_MERGE: ${{ vars.PR_AUTOMATION_ALLOW_FORK_MERGE || 'false' }}" in text
    assert "PR_AUTOMATION_MERGE_WHEN_READY: ${{ vars.PR_AUTOMATION_MERGE_WHEN_READY || 'false' }}" in text
    assert 'PR_AUTOMATION_MAX_MUTATIONS: "1"' in text


def test_workflow_elevates_only_the_evaluate_job_for_status_and_merge_control():
    text = _workflow()
    assert "permissions:\n  contents: read\n" in text
    assert "    permissions:\n      contents: write\n      pull-requests: write\n      statuses: write\n" in text
    assert "actions: write" not in text
    assert "administration: write" not in text
    assert "secrets: write" not in text


def test_manual_pr_input_crosses_shell_boundary_through_env_and_is_validated():
    text = _workflow()
    assert "INPUT_PR: ${{ github.event_name == 'workflow_dispatch' && inputs.pr || '' }}" in text
    assert '[[ "$pr" =~ ^[0-9]+$ ]]' in text
    assert "${{ inputs.pr }}" not in text
