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
ARCHIVED_WORKFLOWS = REPO_ROOT / ".github" / "workflows-archive"


def _event_consumer_source(name: str) -> Path:
    """Exercise active completion consumers, or their retained retired contract."""
    active = WORKFLOWS / name
    archived = ARCHIVED_WORKFLOWS / name
    if active.is_file() and "  workflow_run:" in active.read_text(encoding="utf-8"):
        return active
    return archived if archived.is_file() else active


REPAIR = _event_consumer_source("repair-intake.yml")
AUTOMATION = _event_consumer_source("pr-automation-index.yml")
DRAIN = _event_consumer_source("pr-obsolete-run-drain.yml")
IDLE = _event_consumer_source("idle-studio.yml")
QUEUE_DRAIN = WORKFLOWS / "queue-drain.yml"


def _replace_once(source: str, old: str, new: str) -> str:
    assert old in source, f"fixture marker missing: {old!r}"
    return source.replace(old, new, 1)


def test_live_workflows_satisfy_branch_completion_contract() -> None:
    assert violations(WORKFLOWS) == []


def test_rejects_workflow_run_without_all_branch_globs() -> None:
    source = _replace_once(REPAIR.read_text(encoding="utf-8"), ALL_BRANCH_GLOBS, "branches:\n      - main")
    messages = "\n".join(violations_for_text(REPAIR.name, source))
    assert "every completing head" in messages


def test_pr_automation_may_exclude_only_main_from_workflow_run() -> None:
    source = AUTOMATION.read_text(encoding="utf-8")
    messages = "\n".join(violations_for_text(AUTOMATION.name, source))
    assert "every completing head" not in messages


def test_rejects_pr_automation_broader_branch_exclusion() -> None:
    source = _replace_once(
        AUTOMATION.read_text(encoding="utf-8"),
        "    branches-ignore:\n      - main\n",
        "    branches-ignore:\n      - main\n      - release/**\n",
    )
    messages = "\n".join(violations_for_text(AUTOMATION.name, source))
    assert "every completing head" in messages


def test_queue_drain_may_wake_only_from_guarded_default_branch() -> None:
    source = QUEUE_DRAIN.read_text(encoding="utf-8")
    messages = "\n".join(violations_for_text(QUEUE_DRAIN.name, source))
    assert "every completing head" not in messages
    # No completion event is admitted: recovery happens hourly instead.
    assert "  workflow_run:" not in source
    assert 'cron: "7 * * * *"' in source


def test_rejects_queue_drain_broader_or_unguarded_branch_filter() -> None:
    current = QUEUE_DRAIN.read_text(encoding="utf-8")
    assert "  workflow_run:" not in current
    # A future accidental completion-event trigger must fail closed, even
    # when pointed at main; archived workflow contracts cannot bypass this.
    for branch_filter in ("branches: [release/**]", "branches: [main]"):
        source = _replace_once(
            current,
            "  push:\n",
            '  workflow_run:\n    workflows: ["Merge Readiness"]\n'
            f"    types: [completed]\\n    {branch_filter}\\n".replace("\\n", "\n")
            + "  push:\n",
        )
        messages = "\n".join(violations_for_text(QUEUE_DRAIN.name, source))
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


def test_idle_studio_single_sources_workflow_run_trust_boundary() -> None:
    source = IDLE.read_text(encoding="utf-8")
    guard = "github.event.workflow_run.head_repository.full_name == github.repository"

    assert source.count(guard) == 1
    assert "needs.pressure.result == 'success'" in source
    assert "needs.pressure.outputs.proceed == 'true'" in source


def test_rejects_idle_studio_without_pressure_gate_dependency() -> None:
    source = _replace_once(
        IDLE.read_text(encoding="utf-8"),
        "needs.pressure.result == 'success'",
        "true",
    )
    messages = "\n".join(violations_for_text(IDLE.name, source))
    assert "successful pressure trust gate" in messages


def test_rejects_idle_studio_without_same_repository_head() -> None:
    source = _replace_once(
        IDLE.read_text(encoding="utf-8"),
        "github.event.workflow_run.head_repository.full_name == github.repository",
        "true",
    )
    messages = "\n".join(violations_for_text(IDLE.name, source))
    assert "cross-repository workflow_run trust boundary" in messages


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


def test_default_branch_only_completion_consumers_require_trusted_job_guards() -> None:
    from scripts.check_workflow_run_branch_completions import DEFAULT_BRANCH_CONSUMERS

    for name in sorted(DEFAULT_BRANCH_CONSUMERS):
        source = _event_consumer_source(name).read_text(encoding="utf-8")
        assert violations_for_text(name, source) == []
        if "  workflow_run:" not in source:
            # A retired/manual-only definition has no completion trust gate.
            continue
        unguarded = source.replace(
            "github.event.workflow_run.head_repository.full_name == github.repository",
            "true",
            1,
        )
        assert unguarded != source, name
        messages = "\n".join(violations_for_text(name, unguarded))
        assert "every completing head" in messages, name


def test_unlisted_completion_consumer_cannot_restrict_to_main_without_exemption() -> None:
    from scripts.check_workflow_run_branch_completions import DEFAULT_BRANCH_CONSUMERS

    source = IDLE.read_text(encoding="utf-8")
    assert "  workflow_run:" in source
    assert "branch-clean-fake.yml" not in DEFAULT_BRANCH_CONSUMERS
    messages = "\n".join(violations_for_text("branch-clean-fake.yml", source))
    assert "every completing head" in messages
