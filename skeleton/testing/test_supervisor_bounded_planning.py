"""Fail-closed budgets for large Supervisor observations and provider-free plans."""

from __future__ import annotations

import hashlib
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


def test_live_observation_compacts_large_rollups_without_losing_custody():
    # 40 PRs with verbose check metadata used to exceed canonical_json's
    # 256 KiB snapshot budget before the planner could compact anything.
    statuses = [
        {"name": "check-" + str(i), "conclusion": "SUCCESS",
         "description": "untrusted-check-description-" + ("x" * 1400)}
        for i in range(96)
    ]
    prs = [
        {"number": number, "title": "safe PR", "headRefName": "feature/test",
         "baseRefName": "main", "mergeStateStatus": "BLOCKED",
         "statusCheckRollup": statuses}
        for number in range(1, 41)
    ]

    def observed_gh(args):
        if args[0] == "pr":
            return prs
        return []

    with patch.object(supervisor, "_gh_json", side_effect=observed_gh):
        observed = supervisor.observe("Apeloff1/Skeleton")

    assert len(observed.fingerprint) == 64
    assert len(observed.pull_requests) == 40
    pr = observed.pull_requests[0]
    assert pr["statusCheckRollupCount"] == 96
    assert len(pr["statusCheckRollup"]) == 64
    assert pr["statusCheckRollup"][0] == {"conclusion": "SUCCESS"}
    assert "untrusted-check-description" not in json.dumps(pr)
    assert len(pr["statusCheckRollupFingerprint"]) == 64
    with patch.object(
        supervisor, "_machine_repository_context",
        return_value={"status": "available", "fingerprint": "f" * 64},
    ):
        plan = json.loads(supervisor.deterministic_plan(observed))
    assert plan["snapshot_fingerprint"] == observed.fingerprint

    # Modifying an unshown status still changes the custody identity.
    changed = [dict(item) for item in prs]
    changed[0] = dict(changed[0])
    changed[0]["statusCheckRollup"] = [dict(s) for s in statuses]
    changed[0]["statusCheckRollup"][-1]["conclusion"] = "FAILURE"
    with patch.object(supervisor, "_gh_json", side_effect=lambda args: changed if args[0] == "pr" else []):
        revised = supervisor.observe("Apeloff1/Skeleton")
    assert revised.fingerprint != observed.fingerprint
    assert revised.pull_requests[0]["statusCheckRollup"][:-1] == pr["statusCheckRollup"][:-1]
    assert revised.pull_requests[0]["statusCheckRollup"][-1] == {"conclusion": "FAILURE"}
    assert pr["statusCheckRollup"][-1] == {"conclusion": "SUCCESS"}


def test_pr_rollup_invalid_shape_fails_closed():
    with pytest.raises(supervisor.SupervisorError, match="invalid GitHub PR status"):
        supervisor._normalize_pr_observation({
            "number": 1,
            "statusCheckRollup": {"unexpected": "map"},
        })


def test_large_authorized_snapshot_keeps_full_canonical_hash():
    # Forty individually bounded approved issue bodies plus PR title/CI data
    # exceed the cross-job canonical JSON cap in aggregate. Fingerprinting
    # must remain complete and sensitive to the entire observed state.
    issues = tuple(
        {"number": number, "title": "approved", "body": "x" * 6000,
         "automation_authorized": True}
        for number in range(1, 41)
    )
    prs = tuple(
        {"number": number, "title": "p" * 500, "mergeStateStatus": "BLOCKED"}
        for number in range(1, 41)
    )
    observed = supervisor.SupervisorSnapshot(
        repository="Apeloff1/Skeleton", observed_at=1_700_000_000,
        issues=issues, pull_requests=prs, workflow_runs=(),
    )
    payload = {
        "repository": observed.repository,
        "issues": observed.issues,
        "pull_requests": observed.pull_requests,
        "workflow_runs": observed.workflow_runs,
    }
    raw = json.dumps(
        payload, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False,
    ).encode("utf-8")
    assert len(raw) > 256_000
    assert observed.fingerprint == hashlib.sha256(raw).hexdigest()
    # Existing bounded-envelope controls are unchanged: only the hash is
    # streamed; oversized cross-job JSON must still fail closed.
    with pytest.raises(supervisor.SupervisorError, match="control-plane budget"):
        supervisor._canonical(payload)

    mutated = tuple(dict(item) for item in issues)
    altered = dict(mutated[-1])
    altered["body"] = altered["body"][:-1] + "y"
    mutated = (*mutated[:-1], altered)
    revised = supervisor.SupervisorSnapshot(
        observed.repository, observed.observed_at, mutated,
        observed.pull_requests, observed.workflow_runs,
    )
    assert revised.fingerprint != observed.fingerprint


def test_snapshot_fingerprint_matches_canonical_envelope_hash_on_small_input():
    observed = snapshot(prs=({"number": 2, "title": "stable"},))
    raw = json.dumps(
        {"repository": observed.repository, "issues": observed.issues,
         "pull_requests": observed.pull_requests,
         "workflow_runs": observed.workflow_runs},
        sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False,
    ).encode("utf-8")
    assert observed.fingerprint == hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize("tail_state,expected", [
    ("FAILURE", "failing-ci"),
    ("CANCELLED", "failing-ci"),
    ("QUEUED", "awaiting-checks"),
    ("PENDING", "awaiting-checks"),
    ("UNKNOWN", "awaiting-checks"),
    ("SUCCESS", "healthy"),
])
def test_worker_health_includes_checks_beyond_bounded_rollup(tail_state, expected):
    checks = [{"name": str(i), "conclusion": "SUCCESS"} for i in range(80)]
    checks[-1]["conclusion"] = tail_state
    normalized = supervisor._normalize_pr_observation({
        "number": 77,
        "title": "bounded worker evidence",
        "headRefName": "bot/specialist-builder-" + "a" * 16,
        "baseRefName": "main",
        "mergeStateStatus": "CLEAN",
        "statusCheckRollup": checks,
    })
    assert len(normalized["statusCheckRollup"]) == 64
    assert normalized["statusCheckRollupCount"] == 80
    assert normalized["statusCheckRollup"][0] == {"conclusion": "SUCCESS"}
    # Overflow values are aggregated to a bounded, canonical vocabulary.
    # CANCELLED is deliberately counted as FAILURE, and QUEUED as PENDING.
    canonical = {
        "FAILURE": "FAILURE", "CANCELLED": "FAILURE",
        "QUEUED": "PENDING", "PENDING": "PENDING",
        "UNKNOWN": "UNKNOWN", "SUCCESS": "SUCCESS",
    }
    assert normalized["statusCheckRollup"][-1] == {
        "conclusion": canonical[tail_state]
    }
    health = supervisor.durable_worker_health(snapshot(prs=(normalized,)))
    assert health["active_count"] == 1
    assert health["active_workers"][0]["classification"] == expected
    assert len(normalized["statusCheckRollupFingerprint"]) == 64
