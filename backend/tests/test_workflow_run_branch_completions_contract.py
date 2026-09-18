from __future__ import annotations

from pathlib import Path

from scripts.check_workflow_run_branch_completions import (
    ALL_BRANCH_GLOBS,
    COMMIT_OID_PATTERN,
    HINT_ARRAY_EXPR,
    MISSING_IDENTITY,
    OID_IDENTITY,
    violations,
    violations_for_text,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
REPAIR = WORKFLOWS / "repair-intake.yml"
AUTOMATION = WORKFLOWS / "pr-automation-index.yml"
DRAIN = WORKFLOWS / "pr-obsolete-run-drain.yml"
IDLE = WORKFLOWS / "idle-studio.yml"


def _replace_once(source: str, old: str, new: str) -> str:
    assert old in source, f"fixture marker missing: {old!r}"
    return source.replace(old, new, 1)


def test_live_workflows_satisfy_branch_completion_contract() -> None:
    assert violations(WORKFLOWS) == []


def test_rejects_workflow_run_without_all_branch_globs() -> None:
    source = _replace_once(REPAIR.read_text(encoding="utf-8"), ALL_BRANCH_GLOBS, "branches:\n      - main")
    messages = "\n".join(violations_for_text(REPAIR.name, source))
    assert "every completing head" in messages


def test_rejects_automation_identity_from_first_pull_request_only() -> None:
    source = AUTOMATION.read_text(encoding="utf-8")
    source = _replace_once(
        source,
        HINT_ARRAY_EXPR,
        "github.event.workflow_run.pull_requests[0].number",
    )
    messages = "\n".join(violations_for_text(AUTOMATION.name, source))
    assert "complete pull_requests hint array" in messages
    assert "pull_requests[0] is not a complete branch-completion identity" in messages


def test_rejects_drain_identity_from_first_pull_request_only() -> None:
    source = DRAIN.read_text(encoding="utf-8")
    source = _replace_once(
        source,
        HINT_ARRAY_EXPR,
        "github.event.workflow_run.pull_requests[0].number",
    )
    messages = "\n".join(violations_for_text(DRAIN.name, source))
    assert "complete pull_requests hint array" in messages
    assert "pull_requests[0] is not a complete branch-completion identity" in messages


def test_rejects_loss_of_head_sha_branch_identity() -> None:
    source = _replace_once(
        AUTOMATION.read_text(encoding="utf-8"),
        "github.event.workflow_run.head_sha",
        "github.sha",
    )
    messages = "\n".join(violations_for_text(AUTOMATION.name, source))
    assert "workflow_run.head_sha" in messages


def test_rejects_drain_without_json_hint_env() -> None:
    source = _replace_once(
        DRAIN.read_text(encoding="utf-8"),
        "WORKFLOW_RUN_PR_HINTS",
        "PR_HINTS",
    )
    messages = "\n".join(violations_for_text(DRAIN.name, source))
    assert "JSON PR hints" in messages


def test_rejects_repair_intake_without_complete_identity() -> None:
    source = _replace_once(
        REPAIR.read_text(encoding="utf-8"),
        HINT_ARRAY_EXPR,
        "github.event.workflow_run.pull_requests[0].number",
    )
    assert MISSING_IDENTITY in source
    source = source.replace(MISSING_IDENTITY, "ok")
    messages = "\n".join(violations_for_text(REPAIR.name, source))
    assert "complete pull_requests hint array" in messages
    assert "pull_requests[0] is not a complete branch-completion identity" in messages
    assert "fail closed without head SHA and branch" in messages


def test_rejects_repair_intake_without_commit_oid_canonicalization() -> None:
    source = REPAIR.read_text(encoding="utf-8")
    assert COMMIT_OID_PATTERN in source
    assert OID_IDENTITY in source
    source = _replace_once(source, COMMIT_OID_PATTERN, r"^[0-9a-f]+$")
    messages = "\n".join(violations_for_text(REPAIR.name, source))
    assert "40-hex commit OID" in messages


def test_rejects_idle_studio_without_same_repository_head() -> None:
    source = IDLE.read_text(encoding="utf-8")
    guard = "github.event.workflow_run.head_repository.full_name == github.repository"
    assert guard in source
    source = source.replace(guard, "true")
    messages = "\n".join(violations_for_text(IDLE.name, source))
    assert "cross-repository workflow_run heads" in messages


def test_rejects_idle_studio_without_fail_closed_snapshot_pagination() -> None:
    source = IDLE.read_text(encoding="utf-8")
    source = _replace_once(source, "exceeded bounded identity scan", "truncated ok")
    messages = "\n".join(violations_for_text(IDLE.name, source))
    assert "truncated live snapshots" in messages


def test_rejects_idle_studio_without_base_sha_oid_canonicalization() -> None:
    source = IDLE.read_text(encoding="utf-8")
    assert COMMIT_OID_PATTERN in source
    source = _replace_once(source, COMMIT_OID_PATTERN, r"^[0-9a-f]+$")
    messages = "\n".join(violations_for_text(IDLE.name, source))
    assert "40-hex commit OID" in messages


def test_live_identity_adapters_fail_closed_on_association_http_and_status_oids() -> None:
    drain = (REPO_ROOT / "backend/scripts/pr_obsolete_run_drain.py").read_text(encoding="utf-8")
    runner = (REPO_ROOT / "skeleton/pr_automation/runner.py").read_text(encoding="utf-8")
    sweep = (
        REPO_ROOT / "backend/scripts/pr_obsolete_run_sweep.py"
    ).read_text(encoding="utf-8")
    idle = (REPO_ROOT / "skeleton/automation/idle_studio.py").read_text(encoding="utf-8")
    assert "cache[sha] = False" not in drain
    assert "statuses/{quoted_sha}" in runner
    assert "canonical_commit_oid" in sweep
    assert "canonical_commit_oid" in idle
    assert COMMIT_OID_PATTERN in idle
