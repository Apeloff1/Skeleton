from __future__ import annotations

import base64
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from skeleton.automation import secretary, specialist_bots, supervisor, traffic_manager
from skeleton.automation.advanced_bots import ADVANCED_BOTS
from skeleton.automation.builder_plane import (
    builder_worker_branch,
    compile_builder_manifest,
)
from skeleton.automation.execution_failsafe import retry_token
from skeleton.automation.supervisor_runtime import (
    ExecutionIdentity,
    WorkerCustody,
    canonical_json,
)

ROOT = Path(__file__).resolve().parents[1]
TRAFFIC = ROOT / ".github" / "workflows" / "automation-traffic-manager.yml"
SUPERVISOR = ROOT / ".github" / "workflows" / "supervisor.yml"

REPOSITORY = "Apeloff1/Skeleton"
BASE_SHA = "a" * 40
OBSERVED_AT = 1_800_000_000


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _approved_issue() -> dict[str, Any]:
    return {
        "number": 1685,
        "title": "Advance autonomous repository builder to reliable end-to-end operation",
        "body": (
            "Make the Supervisor -> Secretary -> Worker automation reliably "
            "produce useful reviewable repository improvements with focused "
            "end-to-end tests and operator documentation."
        ),
        "labels": [
            {"name": "build-approved"},
            {"name": "security"},
            {"name": "documentation"},
        ],
        "updatedAt": "2026-09-28T20:00:00Z",
    }


def _execution() -> ExecutionIdentity:
    return ExecutionIdentity(
        repository=REPOSITORY,
        base_sha=BASE_SHA,
        default_branch="main",
        run_id="9001",
        run_attempt="1",
    )


def test_scheduled_admission_reaches_exact_head_supervisor() -> None:
    traffic = _source(TRAFFIC)
    supervisor_source = _source(SUPERVISOR)
    assert 'cron: "*/10 * * * *"' in traffic
    assert '[[ "$live_sha" != "$TRAFFIC_ADMITTED_BASE_SHA" ]]' in traffic
    assert '-f "expected_base_sha=$TRAFFIC_ADMITTED_BASE_SHA"' in traffic
    assert "SUPERVISOR_CALLER_BASE_SHA: ${{ inputs.expected_base_sha }}" in supervisor_source
    assert 'test "$SUPERVISOR_BASE_SHA" = "$SUPERVISOR_CALLER_BASE_SHA"' in supervisor_source


def test_authorized_build_cannot_be_suppressed_by_model_wording() -> None:
    due = [bot.name for bot in ADVANCED_BOTS]
    selected = secretary.route(
        "no feature or implementation keywords are required here",
        due,
        build_authorization=object(),
    )
    assert "feature-builder" in selected


def test_execution_chain_preserves_fail_closed_authority_boundary() -> None:
    supervisor_source = _source(SUPERVISOR)
    assert "permissions: {}" in supervisor_source.split("jobs:", 1)[0]
    assert "contents: write" not in supervisor_source.split("  plan:", 1)[1].split(
        "  secretary:", 1
    )[0]
    secretary_source = supervisor_source.split("  secretary:", 1)[1]
    assert "contents: write" in secretary_source
    assert "SUPERVISOR_DELEGATION_B64" in secretary_source
    assert "python -m skeleton.automation.secretary" in secretary_source


def test_forced_admission_to_pr_publication_and_repeat_convergence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    issue = _approved_issue()
    traffic_snapshot = traffic_manager.TrafficSnapshot(
        repository=REPOSITORY,
        base_sha=BASE_SHA,
        observed_at=OBSERVED_AT,
        current_run_id="42",
        workflow_runs=(),
        pull_requests=(),
        issues=(issue,),
    )
    decision = traffic_manager.evaluate(traffic_snapshot, force=True)
    assert decision.admit is True
    assert decision.base_sha == BASE_SHA
    assert decision.authorized_issues == 1

    normalized_issue = supervisor._normalize_issue(issue)
    supervisor_snapshot = supervisor.SupervisorSnapshot(
        repository=REPOSITORY,
        observed_at=OBSERVED_AT,
        issues=(normalized_issue,),
        pull_requests=(),
        workflow_runs=(),
    )
    execution = _execution()
    plan = "approved_work_items feature implement enhancement"
    envelope = supervisor.make_envelope(supervisor_snapshot, plan, execution)
    assert envelope.build_authorization is not None
    assert envelope.build_authorization.issue_number == 1685

    (
        decoded_plan,
        snapshot_fingerprint,
        decoded_execution,
        build_authorization,
    ) = secretary.decode_delegation(
        envelope.to_base64(),
        repository=REPOSITORY,
        expected_execution=execution,
        now=OBSERVED_AT,
    )
    assert decoded_plan == plan
    assert decoded_execution == execution
    assert build_authorization == envelope.build_authorization

    selected = secretary.route(
        decoded_plan,
        [bot.name for bot in ADVANCED_BOTS],
        build_authorization=build_authorization,
    )
    assert "feature-builder" in selected

    assert build_authorization is not None
    manifest = compile_builder_manifest(
        build_authorization,
        snapshot_fingerprint=snapshot_fingerprint,
        execution=execution,
    )
    expected_branch = builder_worker_branch(manifest)

    runner_temp = tmp_path / "runner"
    runner_temp.mkdir()
    (tmp_path / "docs").mkdir()
    monkeypatch.chdir(tmp_path)

    environment = {
        "GITHUB_REPOSITORY": REPOSITORY,
        "GITHUB_TOKEN": "test-token",
        "SECRETARY_DELEGATION": "1",
        "SECRETARY_WORKER": "feature-builder",
        "SECRETARY_ATTEMPT": "1",
        "SECRETARY_RETRY_TOKEN": retry_token(
            worker="feature-builder",
            attempt=1,
            execution_fingerprint=execution.fingerprint,
            snapshot_fingerprint=snapshot_fingerprint,
        ),
        "SUPERVISOR_SNAPSHOT_FINGERPRINT": snapshot_fingerprint,
        "SUPERVISOR_BASE_SHA": execution.base_sha,
        "SUPERVISOR_DEFAULT_BRANCH": execution.default_branch,
        "SUPERVISOR_RUN_ID": execution.run_id,
        "SUPERVISOR_RUN_ATTEMPT": execution.run_attempt,
        "SUPERVISOR_EXECUTION_FINGERPRINT": execution.fingerprint,
        "SUPERVISOR_BUILD_AUTHORIZATION_B64": base64.b64encode(
            canonical_json(build_authorization.as_dict())
        ).decode("ascii"),
        "SUPERVISOR_BUILD_TASK_DIGEST": build_authorization.task_digest,
        "SUPERVISOR_BUILDER_MANIFEST_B64": manifest.to_base64(),
        "SUPERVISOR_BUILDER_MANIFEST_DIGEST": manifest.manifest_digest,
        "RUNNER_TEMP": str(runner_temp),
    }
    for key, value in environment.items():
        monkeypatch.setenv(key, value)

    monkeypatch.setattr(
        specialist_bots,
        "revalidate_live_build_authorization",
        lambda value: value,
    )
    monkeypatch.setattr(specialist_bots, "require_exact_head", lambda *a, **k: None)
    monkeypatch.setattr(specialist_bots, "require_clean_worktree", lambda *a, **k: None)
    monkeypatch.setattr(
        specialist_bots,
        "require_remote_base_unchanged",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        specialist_bots,
        "find_open_pr_for_worker",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        specialist_bots,
        "find_open_pr_for_head",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        specialist_bots,
        "remote_branch_exists",
        lambda *a, **k: False,
    )
    monkeypatch.setattr(specialist_bots, "FreeModelClient", lambda: object())
    monkeypatch.setattr(
        specialist_bots,
        "run_feature_build",
        lambda **kwargs: {
            "summary": "Close the admitted autonomous builder contract.",
            "files": [
                {
                    "path": "docs/autonomous-builder-e2e-output.md",
                    "content": "# Autonomous builder e2e evidence\n",
                }
            ],
            "tests": ["exercise scheduled admission through PR publication"],
        },
    )
    monkeypatch.setattr(specialist_bots, "_head_text", lambda path: None)
    monkeypatch.setattr(
        specialist_bots,
        "resolve_mutation_target",
        lambda path, **kwargs: tmp_path / path,
    )
    monkeypatch.setattr(
        specialist_bots,
        "validate_staged_paths",
        lambda paths: None,
    )
    monkeypatch.setattr(
        specialist_bots,
        "_verify_single_parent",
        lambda expected: None,
    )

    git_calls: list[list[str]] = []
    gh_calls: list[list[str]] = []
    status_payloads: list[dict[str, Any]] = []

    def fake_run_git(
        args: list[str],
        *,
        env: dict[str, str],
        timeout: int = 30,
    ) -> None:
        assert env["GH_TOKEN"] == "test-token"
        git_calls.append(list(args))

    def fake_subprocess_run(args, **kwargs):
        command = list(args)
        if command[:3] == ["git", "diff", "--cached"]:
            return subprocess.CompletedProcess(command, 1)
        if command[:3] == ["gh", "auth", "setup-git"]:
            gh_calls.append(command)
            return subprocess.CompletedProcess(command, 0)
        if command[:3] == ["gh", "pr", "create"]:
            gh_calls.append(command)
            return subprocess.CompletedProcess(command, 0)
        raise AssertionError(f"unexpected subprocess.run call: {command!r}")

    def fake_check_output(args, **kwargs):
        command = list(args)
        if command[:3] == ["gh", "pr", "view"]:
            return json.dumps(
                {
                    "number": 321,
                    "url": "https://github.com/Apeloff1/Skeleton/pull/321",
                }
            )
        raise AssertionError(f"unexpected subprocess.check_output call: {command!r}")

    monkeypatch.setattr(specialist_bots, "_run_git", fake_run_git)
    monkeypatch.setattr(specialist_bots.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(
        specialist_bots.subprocess,
        "check_output",
        fake_check_output,
    )
    monkeypatch.setattr(specialist_bots, "_print_status", status_payloads.append)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "specialist_bots",
            "--bot",
            "feature-builder",
            "--plan",
            decoded_plan,
        ],
    )

    assert specialist_bots.main() == 0
    assert (tmp_path / "docs" / "autonomous-builder-e2e-output.md").is_file()
    assert status_payloads[-1]["status"] == "pull-request-created"
    assert status_payloads[-1]["branch"] == expected_branch
    assert status_payloads[-1]["pull_request"] == 321
    assert status_payloads[-1]["pull_request_url"].endswith("/pull/321")
    assert status_payloads[-1]["build_issue_number"] == 1685
    assert status_payloads[-1]["builder_manifest_digest"] == manifest.manifest_digest
    assert status_payloads[-1]["builder_proposal_receipt"] is not None

    assert any("switch" in command and expected_branch in command for command in git_calls)
    assert any("commit" in command for command in git_calls)
    assert any("push" in command and expected_branch in command for command in git_calls)

    pr_create = next(
        command for command in gh_calls if command[:3] == ["gh", "pr", "create"]
    )
    assert pr_create[pr_create.index("--head") + 1] == expected_branch
    body = pr_create[pr_create.index("--body") + 1]
    assert "Closes #1685" in body
    assert build_authorization.task_digest in body

    active_pr = {
        "number": 321,
        "headRefName": expected_branch,
        "baseRefName": "main",
    }
    monkeypatch.setattr(
        specialist_bots,
        "find_open_pr_for_worker",
        lambda *a, **k: active_pr,
    )
    custody = WorkerCustody(
        worker="feature-builder",
        snapshot_fingerprint=snapshot_fingerprint,
        execution=execution,
    )
    repeated_branch, repeated_pr = specialist_bots._preflight(
        custody,
        builder_manifest=manifest,
    )
    assert repeated_branch == expected_branch
    assert repeated_pr == active_pr


def test_operator_contract_documents_terminal_and_recovery_states() -> None:
    source = (ROOT / "docs" / "AUTONOMOUS_BUILDER_OPERATIONS.md").read_text(
        encoding="utf-8"
    )
    for marker in (
        "capacity-suppressed",
        "missing-demand",
        "provider-failure",
        "stale-custody",
        "validation-failure",
        "publication-failure",
        "pull-request-created",
        "existing-pr",
    ):
        assert marker in source
