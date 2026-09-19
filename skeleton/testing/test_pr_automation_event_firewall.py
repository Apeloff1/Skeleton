from __future__ import annotations

import json
import os
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

import pytest

from skeleton.pr_automation import runner
from skeleton.pr_automation.event_firewall import (
    AdmissionLevel,
    EventFirewallError,
    EventFirewallPolicy,
    WorkflowRunEvent,
    admit_workflow_run,
    event_from_env,
    parse_pr_hints,
)


SHA = "a" * 40


def event(
    *,
    repository: str = "Apeloff1/Skeleton",
    upstream_workflow: str = "Merge Readiness",
    run_id: int = 100,
    run_attempt: int = 1,
    workflow_id: int = 200,
    status: str = "completed",
    conclusion: str = "success",
    source_event: str = "pull_request",
    head_repository: str = "Apeloff1/Skeleton",
    head_branch: str = "feature/security",
    head_sha: str = SHA,
    pr_hints: tuple[int, ...] = (123,),
) -> WorkflowRunEvent:
    return WorkflowRunEvent(
        repository=repository,
        upstream_workflow=upstream_workflow,
        run_id=run_id,
        run_attempt=run_attempt,
        workflow_id=workflow_id,
        status=status,
        conclusion=conclusion,
        source_event=source_event,
        head_repository=head_repository,
        head_branch=head_branch,
        head_sha=head_sha,
        pr_hints=pr_hints,
    )


def workflow_env(**overrides: str) -> dict[str, str]:
    values = {
        "WORKFLOW_RUN_NAME": "Merge Readiness",
        "WORKFLOW_RUN_ID": "100",
        "WORKFLOW_RUN_ATTEMPT": "1",
        "WORKFLOW_RUN_WORKFLOW_ID": "200",
        "WORKFLOW_RUN_STATUS": "completed",
        "WORKFLOW_RUN_CONCLUSION": "success",
        "WORKFLOW_RUN_EVENT": "pull_request",
        "WORKFLOW_RUN_HEAD_REPOSITORY": "Apeloff1/Skeleton",
    }
    values.update(overrides)
    return values


def test_successful_same_repo_pr_completion_can_reach_downstream_mutation_policy() -> None:
    decision = admit_workflow_run(event())

    assert decision.level is AdmissionLevel.MUTATE
    assert decision.mutation_authorized
    assert not decision.dropped
    assert len(decision.event_fingerprint) == 64


@pytest.mark.parametrize(
    "conclusion",
    [
        "failure",
        "neutral",
        "skipped",
        "timed_out",
        "action_required",
        "startup_failure",
        "stale",
    ],
)
def test_non_success_completion_is_observation_only(conclusion: str) -> None:
    decision = admit_workflow_run(event(conclusion=conclusion))

    assert decision.level is AdmissionLevel.OBSERVE
    assert not decision.mutation_authorized
    assert not decision.dropped


def test_cancelled_completion_is_dropped_as_superseded_tombstone() -> None:
    decision = admit_workflow_run(event(conclusion="cancelled"))

    assert decision.level is AdmissionLevel.DROP
    assert decision.dropped
    assert not decision.mutation_authorized
    assert "tombstone" in decision.reason


@pytest.mark.parametrize(
    "source_event",
    ["workflow_dispatch", "push", "schedule"],
)
def test_non_pr_upstream_trigger_is_observation_only(source_event: str) -> None:
    decision = admit_workflow_run(event(source_event=source_event))

    assert decision.level is AdmissionLevel.OBSERVE
    assert "trigger class" in decision.reason


def test_cross_repository_completion_is_observation_only() -> None:
    decision = admit_workflow_run(
        event(head_repository="ExternalContributor/Skeleton")
    )

    assert decision.level is AdmissionLevel.OBSERVE
    assert "cross-repository" in decision.reason


def test_untrusted_upstream_workflow_is_dropped() -> None:
    decision = admit_workflow_run(
        event(upstream_workflow="Unknown Workflow")
    )

    assert decision.level is AdmissionLevel.DROP
    assert "not trusted" in decision.reason


def test_policy_can_name_multiple_exact_trusted_upstreams() -> None:
    policy = EventFirewallPolicy(
        trusted_upstream_workflows=frozenset(
            {"Merge Readiness", "Emergency Readiness"}
        )
    )

    decision = admit_workflow_run(
        event(upstream_workflow="Emergency Readiness"),
        policy=policy,
    )

    assert decision.level is AdmissionLevel.MUTATE


def test_workflow_name_matching_is_exact_not_case_folded() -> None:
    decision = admit_workflow_run(
        event(upstream_workflow="merge readiness")
    )

    assert decision.level is AdmissionLevel.DROP


@pytest.mark.parametrize(
    "repository",
    [
        "",
        "owner",
        "/repo",
        "owner/",
        "owner/repo/extra",
        "owner with space/repo",
    ],
)
def test_repository_identity_is_strict(repository: str) -> None:
    with pytest.raises(EventFirewallError):
        event(repository=repository)


@pytest.mark.parametrize(
    "sha",
    [
        "",
        "a" * 39,
        "a" * 41,
        "g" * 40,
        "A" * 40,
    ],
)
def test_head_sha_requires_full_lowercase_commit_oid(sha: str) -> None:
    with pytest.raises(EventFirewallError):
        event(head_sha=sha)


@pytest.mark.parametrize(
    "branch",
    [
        "",
        "../escape",
        "/leading",
        "trailing/",
        "double//slash",
        "bad@{ref",
        "space branch",
        "branch.lock",
    ],
)
def test_head_branch_rejects_ambiguous_or_dangerous_ref_shapes(
    branch: str,
) -> None:
    with pytest.raises(EventFirewallError):
        event(head_branch=branch)


def test_pr_hints_are_positive_unique_and_bounded() -> None:
    item = event(pr_hints=(1, 2, 2, 3))
    assert item.pr_hints == (1, 2, 3)

    with pytest.raises(EventFirewallError):
        event(pr_hints=(0,))
    with pytest.raises(EventFirewallError):
        event(pr_hints=tuple(range(1, 66)))


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", ()),
        ("null", ()),
        ("[]", ()),
        ("[1]", (1,)),
        ("[1,2,2,3]", (1, 2, 3)),
    ],
)
def test_parse_pr_hints(raw: str, expected: tuple[int, ...]) -> None:
    assert parse_pr_hints(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "{}",
        '"1"',
        "[0]",
        "[-1]",
        "[true]",
        "[1.5]",
        "not-json",
    ],
)
def test_parse_pr_hints_rejects_malformed_or_non_positive_values(raw: str) -> None:
    with pytest.raises(EventFirewallError):
        parse_pr_hints(raw)


def test_event_fingerprint_changes_with_run_attempt() -> None:
    first = event(run_attempt=1)
    second = event(run_attempt=2)
    assert first.fingerprint != second.fingerprint


def test_event_fingerprint_changes_with_commit() -> None:
    first = event(head_sha="a" * 40)
    second = event(head_sha="b" * 40)
    assert first.fingerprint != second.fingerprint


def test_event_from_env_requires_all_authority_fields() -> None:
    values = workflow_env()
    parsed = event_from_env(
        values,
        repository="Apeloff1/Skeleton",
        head_sha=SHA,
        head_branch="feature/security",
        pr_hints_json="[123]",
    )

    assert parsed.upstream_workflow == "Merge Readiness"
    assert parsed.run_id == 100
    assert parsed.run_attempt == 1
    assert parsed.workflow_id == 200
    assert parsed.conclusion == "success"
    assert parsed.source_event == "pull_request"
    assert parsed.pr_hints == (123,)


@pytest.mark.parametrize(
    "missing",
    [
        "WORKFLOW_RUN_NAME",
        "WORKFLOW_RUN_ID",
        "WORKFLOW_RUN_ATTEMPT",
        "WORKFLOW_RUN_WORKFLOW_ID",
        "WORKFLOW_RUN_STATUS",
        "WORKFLOW_RUN_CONCLUSION",
        "WORKFLOW_RUN_EVENT",
        "WORKFLOW_RUN_HEAD_REPOSITORY",
    ],
)
def test_missing_workflow_run_authority_field_fails_closed(missing: str) -> None:
    values = workflow_env()
    values.pop(missing)

    with pytest.raises(EventFirewallError):
        event_from_env(
            values,
            repository="Apeloff1/Skeleton",
            head_sha=SHA,
            head_branch="feature/security",
            pr_hints_json="[123]",
        )


def test_cancelled_runner_event_returns_before_github_client_or_token_use() -> None:
    output = StringIO()
    environment = {
        **workflow_env(WORKFLOW_RUN_CONCLUSION="cancelled"),
        "SKELETON_AUTOMATION_PAUSED": "false",
        "SKELETON_AUTOMATION_QUARANTINED": "false",
        "GITHUB_TOKEN": "",
        "PR_AUTOMATION_MODE": "apply",
    }

    with patch.dict(os.environ, environment, clear=False), patch.object(
        runner.GitHubClient,
        "__init__",
        side_effect=AssertionError("GitHubClient must not be constructed"),
    ), redirect_stdout(output):
        result = runner.main(
            [
                "--repo",
                "Apeloff1/Skeleton",
                "--head-sha",
                SHA,
                "--head-ref",
                "feature/security",
                "--pr-hints-json",
                "[123]",
            ]
        )

    assert result == 0
    payload = json.loads(output.getvalue())
    assert payload["kind"] == "pr-automation-event-admission"
    assert payload["level"] == "drop"


def test_observation_only_event_forces_observe_mode_before_run_one() -> None:
    environment = {
        **workflow_env(WORKFLOW_RUN_CONCLUSION="failure"),
        "SKELETON_AUTOMATION_PAUSED": "false",
        "SKELETON_AUTOMATION_QUARANTINED": "false",
        "GITHUB_TOKEN": "fixture-token",
        "PR_AUTOMATION_MODE": "apply",
        "PR_AUTOMATION_REQUIRED_CHECKS": "Merge Readiness",
    }

    observed_modes = []

    with patch.dict(os.environ, environment, clear=False), patch.object(
        runner,
        "GitHubClient",
        return_value=object(),
    ), patch.object(
        runner,
        "EventIndex",
    ) as index_type, patch.object(
        runner,
        "select_evaluation_targets",
        return_value=[123],
    ), patch.object(
        runner,
        "run_one",
    ) as run_one:
        run_one.return_value = runner.ActionOutcome(
            mutations=0,
            snapshot=object(),  # type: ignore[arg-type]
            evaluation=object(),  # type: ignore[arg-type]
        )

        def capture(*_args, **kwargs):
            observed_modes.append(kwargs["mode"])
            return run_one.return_value

        run_one.side_effect = capture
        index_type.return_value.export_jsonl.return_value = None

        result = runner.main(
            [
                "--repo",
                "Apeloff1/Skeleton",
                "--head-sha",
                SHA,
                "--head-ref",
                "feature/security",
                "--pr-hints-json",
                "[123]",
            ]
        )

    assert result == 0
    assert observed_modes == [runner.Mode.OBSERVE]


def test_successful_pr_event_preserves_requested_apply_mode() -> None:
    environment = {
        **workflow_env(WORKFLOW_RUN_CONCLUSION="success"),
        "SKELETON_AUTOMATION_PAUSED": "false",
        "SKELETON_AUTOMATION_QUARANTINED": "false",
        "GITHUB_TOKEN": "fixture-token",
        "PR_AUTOMATION_MODE": "apply",
        "PR_AUTOMATION_REQUIRED_CHECKS": "Merge Readiness",
        "PR_AUTOMATION_MERGE_WHEN_READY": "false",
    }

    observed_modes = []
    with patch.dict(os.environ, environment, clear=False), patch.object(
        runner,
        "GitHubClient",
        return_value=object(),
    ), patch.object(
        runner,
        "EventIndex",
    ) as index_type, patch.object(
        runner,
        "select_evaluation_targets",
        return_value=[123],
    ), patch.object(
        runner,
        "run_one",
    ) as run_one:
        run_one.return_value = runner.ActionOutcome(
            mutations=0,
            snapshot=object(),  # type: ignore[arg-type]
            evaluation=object(),  # type: ignore[arg-type]
        )

        def capture(*_args, **kwargs):
            observed_modes.append(kwargs["mode"])
            return run_one.return_value

        run_one.side_effect = capture
        index_type.return_value.export_jsonl.return_value = None

        assert (
            runner.main(
                [
                    "--repo",
                    "Apeloff1/Skeleton",
                    "--head-sha",
                    SHA,
                    "--head-ref",
                    "feature/security",
                    "--pr-hints-json",
                    "[123]",
                ]
            )
            == 0
        )

    assert observed_modes == [runner.Mode.APPLY]


def test_workflow_exports_complete_authority_metadata_through_env() -> None:
    from pathlib import Path

    text = Path(".github/workflows/pr-automation-index.yml").read_text(
        encoding="utf-8"
    )
    for name in (
        "WORKFLOW_RUN_ID",
        "WORKFLOW_RUN_ATTEMPT",
        "WORKFLOW_RUN_WORKFLOW_ID",
        "WORKFLOW_RUN_NAME",
        "WORKFLOW_RUN_STATUS",
        "WORKFLOW_RUN_CONCLUSION",
        "WORKFLOW_RUN_EVENT",
        "WORKFLOW_RUN_HEAD_REPOSITORY",
    ):
        assert f"{name}:" in text


def test_workflow_does_not_interpolate_authority_metadata_directly_into_shell() -> None:
    from pathlib import Path

    text = Path(".github/workflows/pr-automation-index.yml").read_text(
        encoding="utf-8"
    )
    dollar = "$"
    assert dollar + "{{ github.event.workflow_run.name }}" not in text
    assert dollar + "{{ github.event.workflow_run.conclusion }}" not in text
    assert (
        dollar + "{{ github.event.workflow_run.head_repository.full_name }}"
        not in text
    )
