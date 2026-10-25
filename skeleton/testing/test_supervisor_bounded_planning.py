"""Fail-closed budgets for large Supervisor observations and provider-free plans."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from skeleton.automation import supervisor
from skeleton.automation.supervisor_runtime import ExecutionIdentity


def snapshot(*, prs=(), runs=()):
    return supervisor.SupervisorSnapshot(
        repository="Apeloff1/Skeleton",
        observed_at=1_700_000_000,
        issues=(),
        pull_requests=tuple(prs),
        workflow_runs=tuple(runs),
    )


def execution():
    return ExecutionIdentity(
        repository="Apeloff1/Skeleton",
        base_sha="b" * 40,
        default_branch="main",
        run_id="42",
        run_attempt="1",
    )


def test_fallback_compacts_massive_machine_context_without_losing_custody():
    observed = snapshot(prs=({"number": 7, "mergeStateStatus": "BLOCKED"},))
    machine = {
        "status": "available",
        "fingerprint": "f" * 64,
        "context_shards": ["s" * 330_000],
        "work_candidates": [{"id": "bounded-candidate", "source": "repository"}],
    }
    with patch.object(supervisor, "_machine_repository_context", return_value=machine):
        first = supervisor.deterministic_plan(observed)
        second = supervisor.deterministic_plan(observed)

    assert first == second
    assert len(first.encode("utf-8")) <= supervisor.MAX_PLAN_BYTES
    plan = json.loads(first)
    assert plan["snapshot_fingerprint"] == observed.fingerprint
    assert plan["priority_observations"]["blocked_pull_requests"][0]["number"] == 7
    repo = plan["priority_observations"]["machine_repository"]
    assert repo["fingerprint"] == machine["fingerprint"]
    assert repo["work_candidates"] == machine["work_candidates"]
    assert "context_shards" in repo["deferred_fields"]
    assert "context_shards" in machine  # no modification of observation
    envelope = supervisor.make_envelope(observed, first, execution())
    assert len(envelope.to_base64()) > 0


def test_model_context_remains_valid_json_and_keeps_exact_snapshot_fingerprint():
    # GitHub statusCheckRollup may contain many historical check contexts.
    large_status = [{"name": "validation", "description": "q" * 3500}] * 25
    prs = ({
        "number": 7,
        "title": "Existing current-head PR",
        "headRefName": "fix/a",
        "mergeStateStatus": "BLOCKED",
        "statusCheckRollup": large_status,
    },)
    observed = snapshot(prs=prs)
    with patch.object(
        supervisor,
        "_machine_repository_context",
        return_value={"status": "available", "fingerprint": "f" * 64},
    ):
        result = supervisor._context(observed)

    assert len(result.encode("utf-8")) <= supervisor.MAX_CONTEXT_BYTES
    parsed = json.loads(result)
    assert parsed["snapshot_fingerprint"] == observed.fingerprint
    assert parsed["pull_requests"][0]["number"] == 7
    assert "pull_requests" in parsed["reduced_observation_fields"]
    assert "statusCheckRollup" not in parsed["pull_requests"][0]
    assert "statusCheckRollup" in observed.pull_requests[0]


def test_priority_failure_receipts_fit_without_breaking_json():
    verbose_checks = [{"name": "required", "status": "failure", "details": "x" * 6000}]
    blocked = tuple(
        {
            "number": i,
            "title": "blocked-PR-" + str(i),
            "mergeStateStatus": "BLOCKED",
            "statusCheckRollup": verbose_checks,
        }
        for i in range(8)
    )
    observed = snapshot(prs=blocked)
    with patch.object(
        supervisor,
        "_machine_repository_context",
        return_value={"status": "available", "fingerprint": "f" * 64},
    ):
        plan = json.loads(supervisor.deterministic_plan(observed))
    assert plan["snapshot_fingerprint"] == observed.fingerprint
    assert plan["priority_observations"]["open_pull_request_count"] == 8
    assert "blocked_pull_requests" in plan["priority_observations"]["reduced_observation_fields"]
    assert plan["priority_observations"]["blocked_pull_requests"][0]["number"] == 0


def test_immutable_oversize_cannot_be_truncated_or_admitted():
    with pytest.raises(supervisor.SupervisorError, match="budget"):
        supervisor._bounded_planning_json(
            {
                "version": 1,
                "immutable_authority": "Z" * 20_000,
                "priority_observations": {"machine_repository": {"status": "available"}},
            },
            max_bytes=300,
        )



def test_oversized_provider_plan_never_reaches_secretary_truncated():
    observed = snapshot(prs=({"number": 7, "mergeStateStatus": "BLOCKED"},))
    # The original branch cut the last bytes without validation. That could
    # change an authorization constraint or produce an incomplete JSON plan.
    oversized = '{"proposal":"' + ("a" * (supervisor.MAX_PLAN_BYTES + 1024)) + '"}'
    with (
        patch.object(supervisor, "FreeModelClient") as fake_client,
        patch.object(
            supervisor,
            "_machine_repository_context",
            return_value={"status": "available", "fingerprint": "f" * 64},
        ),
    ):
        fake_client.return_value.chat.return_value = oversized
        plan = supervisor.model_plan(observed)

    parsed = json.loads(plan)
    assert parsed["snapshot_fingerprint"] == observed.fingerprint
    assert parsed["version"] == 1
    assert parsed["priority_observations"]["blocked_pull_requests"][0]["number"] == 7
    assert "a" * 100 not in plan
    assert len(plan.encode("utf-8")) <= supervisor.MAX_PLAN_BYTES
    assert supervisor.make_envelope(observed, plan, execution()).to_base64()
