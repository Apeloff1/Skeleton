"""Contract and validation regressions for PR automation runner v2."""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import timedelta
import json

import pytest

from skeleton.pr_automation.core import Decision, Mode
from skeleton.pr_automation.runner_contracts import (
    AdmissionDecision,
    AdmissionState,
    CheckEvidence,
    CheckState,
    EvidenceCompleteness,
    FileEvidence,
    MutationIntent,
    MutationReceipt,
    MutationState,
    Preconditions,
    PriorityBand,
    RequestKind,
    RequestOutcome,
    RequestRecord,
    ReviewEvidence,
    RunBudget,
    RunIdentity,
    RunnerLimits,
    RunnerPolicy,
    RunTrigger,
    Target,
    TargetResult,
    TargetSet,
    TransportSummary,
    WorkState,
    bounded_text,
    canonical_json,
    ci_state_from_checks,
    fingerprint,
    parse_time,
    snapshot_policy_fingerprint,
    unique_text,
    valid_context,
    valid_ref,
    valid_repository,
    valid_sha,
)
from skeleton.testing.runner_v2_test_support import (
    NOW,
    SHA_A,
    SHA_B,
    core_policy,
    limits,
    runner_policy,
    snapshot,
    work_item,
)


@pytest.mark.parametrize(
    "value,expected",
    [
        (SHA_A, True),
        ("A" * 40, False),
        ("a" * 39, False),
        ("a" * 41, False),
        ("g" * 40, False),
        ("", False),
    ],
)
def test_valid_sha_is_canonical(value, expected):
    assert valid_sha(value) is expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("Apeloff1/Skeleton", True),
        ("a/b", True),
        ("a_b/c-d", True),
        ("missing-slash", False),
        ("a/b/c", False),
        ("/repo", False),
        ("owner/", False),
    ],
)
def test_repository_validation(value, expected):
    assert valid_repository(value) is expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("main", True),
        ("feature/runner-v2", True),
        ("release/2026.09", True),
        ("refs/heads/main", True),
        ("a//b", False),
        ("a/../b", False),
        ("a.lock", False),
        ("a/b.lock", False),
        ("/main", False),
        ("main/", False),
        ("main.", False),
        ("x@{1}", False),
    ],
)
def test_ref_validation(value, expected):
    assert valid_ref(value) is expected


def test_context_validation_rejects_controls():
    assert valid_context("Merge Readiness")
    assert not valid_context("")
    assert not valid_context("bad\ncontext")
    assert not valid_context("bad\x00context")


def test_canonical_json_is_order_stable():
    left = {"b": 2, "a": [1, 3]}
    right = {"a": [1, 3], "b": 2}
    assert canonical_json(left) == canonical_json(right)
    assert fingerprint(left) == fingerprint(right)


def test_fingerprint_changes_on_material_change():
    assert fingerprint({"a": 1}) != fingerprint({"a": 2})


@pytest.mark.parametrize(
    "value",
    [
        "2026-09-20T00:00:00Z",
        "2026-09-20T00:00:00+00:00",
        "2026-09-20T02:00:00+02:00",
    ],
)
def test_parse_time_returns_utc(value):
    parsed = parse_time(value)
    assert parsed is not None
    assert parsed.utcoffset().total_seconds() == 0


@pytest.mark.parametrize("value", [None, "", "not-a-time"])
def test_parse_time_invalid_returns_none(value):
    assert parse_time(value) is None


def test_bounded_text_truncates():
    assert bounded_text("abcdef", limit=3) == "abc"


def test_bounded_text_rejects_negative_limit():
    with pytest.raises(ValueError):
        bounded_text("x", limit=-1)


def test_unique_text_preserves_first_occurrence():
    assert unique_text(("b", "a", "b")) == ("b", "a")


def test_unique_text_casefolds_before_deduplication():
    assert unique_text(("AutoMerge", "automerge"), casefold=True) == (
        "automerge",
    )


def test_unique_text_rejects_empty():
    with pytest.raises(ValueError):
        unique_text(("ok", " "))


def test_unique_text_enforces_bound():
    with pytest.raises(ValueError):
        unique_text(("a", "b"), max_items=1)


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_targets", 0),
        ("max_requests", 0),
        ("max_graphql_requests", 0),
        ("max_pages", 0),
        ("max_response_bytes", 0),
        ("deadline_seconds", 0),
        ("per_target_request_budget", 0),
        ("minimum_rate_remaining", 0),
        ("retry_ceiling_seconds", 0),
    ],
)
def test_runner_limits_require_positive_values(field, value):
    with pytest.raises(ValueError):
        replace(limits(), **{field: value})


@pytest.mark.parametrize("value", [-1, True])
def test_runner_limits_mutations_non_negative(value):
    with pytest.raises(ValueError):
        replace(limits(), max_mutations=value)


@pytest.mark.parametrize("value", [-1, True])
def test_runner_limits_queue_threshold_non_negative(value):
    with pytest.raises(ValueError):
        replace(limits(), queue_pressure_threshold=value)


@pytest.mark.parametrize("value", [-1, 11, True])
def test_runner_limits_retry_attempt_bound(value):
    with pytest.raises(ValueError):
        replace(limits(), retry_attempts=value)


def test_runner_policy_normalizes_labels_and_authors():
    policy = RunnerPolicy(
        core=core_policy(),
        mode=Mode.APPLY,
        required_checks=("Merge Readiness",),
        allowed_authors=("Apeloff1", "apeloff1"),
        denied_labels=("DO-NOT-MERGE",),
        required_labels=("AutoMerge",),
        limits=limits(),
    )
    assert policy.allowed_authors == ("apeloff1",)
    assert policy.denied_labels == ("do-not-merge",)
    assert policy.required_labels == ("automerge",)


@pytest.mark.parametrize("method", ["octopus", "", "SQUASH"])
def test_runner_policy_merge_method_strict(method):
    with pytest.raises(ValueError):
        replace(runner_policy(), merge_method=method)


def test_runner_policy_fingerprint_changes_with_mode():
    assert runner_policy().fingerprint() != replace(
        runner_policy(),
        mode=Mode.OBSERVE,
    ).fingerprint()


def test_run_identity_requires_repository():
    with pytest.raises(ValueError):
        RunIdentity(
            repository="broken",
            delivery_id="1",
            trigger=RunTrigger.RECOVERY,
        )


def test_run_identity_requires_delivery():
    with pytest.raises(ValueError):
        RunIdentity(
            repository="a/b",
            delivery_id="",
            trigger=RunTrigger.RECOVERY,
        )


def test_run_identity_rejects_partial_workflow_identity():
    with pytest.raises(ValueError):
        RunIdentity(
            repository="a/b",
            delivery_id="1",
            trigger=RunTrigger.WORKFLOW_COMPLETION,
            head_sha=SHA_A,
        )


def test_run_identity_rejects_bad_sha():
    with pytest.raises(ValueError):
        RunIdentity(
            repository="a/b",
            delivery_id="1",
            trigger=RunTrigger.WORKFLOW_COMPLETION,
            head_sha="A" * 40,
            head_ref="feature/x",
        )


def test_run_identity_rejects_bad_pr_number():
    with pytest.raises(ValueError):
        RunIdentity(
            repository="a/b",
            delivery_id="1",
            trigger=RunTrigger.EXPLICIT,
            explicit_pr=0,
        )


def test_run_identity_fingerprint_stable():
    first = RunIdentity(
        repository="a/b",
        delivery_id="1",
        trigger=RunTrigger.RECOVERY,
    )
    second = RunIdentity(
        repository="a/b",
        delivery_id="1",
        trigger=RunTrigger.RECOVERY,
    )
    assert first.fingerprint() == second.fingerprint()


def test_admission_properties():
    decision = AdmissionDecision(
        state=AdmissionState.OBSERVE_ONLY,
        reasons=("observe",),
        mutation_authorized=False,
        priority=PriorityBand.SWEEP,
        identity_fingerprint="x" * 64,
    )
    assert decision.observe_only
    assert not decision.dropped


@pytest.mark.parametrize(
    "sequence,attempt,response_bytes",
    [
        (0, 1, 0),
        (1, 0, 0),
        (1, 1, -1),
    ],
)
def test_request_record_validates_counters(sequence, attempt, response_bytes):
    with pytest.raises(ValueError):
        RequestRecord(
            sequence=sequence,
            method="GET",
            url="https://api.github.com/x",
            kind=RequestKind.READ,
            outcome=RequestOutcome.SUCCESS,
            status_code=200,
            attempt=attempt,
            started_at=NOW.isoformat(),
            finished_at=NOW.isoformat(),
            response_bytes=response_bytes,
            rate_limit_remaining=10,
            retry_after_seconds=None,
        )


def test_transport_summary_rejects_negative():
    with pytest.raises(ValueError):
        TransportSummary(
            requests=-1,
            graphql_requests=0,
            retries=0,
            bytes_received=0,
            rate_limited=0,
            failures=0,
            minimum_remaining_seen=None,
        )


def test_check_evidence_validates_head_sha():
    with pytest.raises(ValueError):
        CheckEvidence(
            name="CI/CD",
            provider="actions",
            state=CheckState.PASSING,
            source="check",
            source_id=1,
            head_sha="bad",
            started_at=None,
            completed_at=None,
            updated_at=None,
        )


def test_check_evidence_recency_uses_completion():
    item = CheckEvidence(
        name="CI/CD",
        provider="actions",
        state=CheckState.PASSING,
        source="check",
        source_id=9,
        head_sha=SHA_A,
        started_at="a",
        completed_at="c",
        updated_at="b",
    )
    assert item.recency() == ("c", 9)


def test_review_evidence_validates_commit():
    with pytest.raises(ValueError):
        ReviewEvidence(
            login="reviewer",
            state="APPROVED",
            review_id=1,
            commit_id="bad",
            submitted_at=None,
        )


def test_file_evidence_rejects_absolute_path():
    with pytest.raises(ValueError):
        FileEvidence(
            filename="/etc/passwd",
            status="modified",
            additions=1,
            deletions=0,
            changes=1,
        )


@pytest.mark.parametrize("field", ["additions", "deletions", "changes"])
def test_file_evidence_rejects_negative_metrics(field):
    kwargs = dict(
        filename="a.py",
        status="modified",
        additions=1,
        deletions=1,
        changes=2,
    )
    kwargs[field] = -1
    with pytest.raises(ValueError):
        FileEvidence(**kwargs)


def test_completeness_reports_missing_fields():
    value = EvidenceCompleteness(
        pull_request=True,
        checks=False,
        statuses=True,
        reviews=False,
        threads=True,
        files=True,
        base_branch=True,
        base_head=False,
    )
    assert not value.complete
    assert value.missing() == ("checks", "reviews", "base_head")


def test_runner_snapshot_requires_file_count_match_when_complete():
    snap = snapshot()
    with pytest.raises(ValueError):
        replace(
            snap,
            files=(),
        )


def test_runner_snapshot_fingerprint_changes_on_check_state():
    snap = snapshot()
    changed = replace(
        snap,
        required_check_states=(
            ("Merge Readiness", CheckState.FAILING),
            ("CI/CD", CheckState.PASSING),
        ),
    )
    assert snap.fingerprint() != changed.fingerprint()


def test_runner_snapshot_same_repository_casefolded():
    snap = replace(snapshot(), head_repository="apeloff1/skeleton")
    assert snap.same_repository_head


def test_runner_snapshot_exact_base_head():
    assert snapshot().exact_base_head
    assert not replace(snapshot(), base_head_sha=SHA_B).exact_base_head


@pytest.mark.parametrize("number", [0, -1, True])
def test_target_number_positive(number):
    with pytest.raises(ValueError):
        Target(
            number=number,
            reason="x",
            priority=PriorityBand.SWEEP,
        )


def test_target_set_rejects_duplicates():
    with pytest.raises(ValueError):
        TargetSet(
            repository="a/b",
            targets=(
                Target(1, "x", PriorityBand.SWEEP),
                Target(1, "y", PriorityBand.SWEEP),
            ),
            complete=True,
            reason="x",
            requests_used=0,
        )


def test_run_budget_remaining_methods():
    budget = RunBudget(
        request_limit=10,
        graphql_limit=5,
        mutation_limit=2,
        target_limit=3,
        deadline_at=(NOW + timedelta(minutes=5)).isoformat(),
        request_used=3,
        graphql_used=1,
        mutations_used=1,
        targets_used=2,
    )
    assert budget.remaining_requests() == 7
    assert budget.remaining_graphql() == 4
    assert budget.remaining_mutations() == 1
    assert budget.remaining_targets() == 1


def test_run_budget_rejects_used_over_limit():
    with pytest.raises(ValueError):
        RunBudget(
            request_limit=1,
            graphql_limit=1,
            mutation_limit=1,
            target_limit=1,
            deadline_at=NOW.isoformat(),
            request_used=2,
        )


def test_preconditions_satisfied_only_when_all_true():
    value = Preconditions(
        protected_base=True,
        base_head_matches=True,
        head_matches=True,
        snapshot_matches=True,
        policy_matches=True,
        checks_still_passing=True,
        reviews_still_valid=True,
        queue_within_limit=True,
        rate_limit_safe=True,
    )
    assert value.satisfied
    assert value.failed() == ()


def test_preconditions_failed_names():
    value = Preconditions(
        protected_base=False,
        base_head_matches=True,
        head_matches=False,
        snapshot_matches=True,
        policy_matches=True,
        checks_still_passing=True,
        reviews_still_valid=True,
        queue_within_limit=True,
        rate_limit_safe=True,
    )
    assert not value.satisfied
    assert value.failed() == ("protected_base", "head_matches")


def test_mutation_intent_is_deterministic():
    item = work_item()
    policy = runner_policy()
    first = MutationIntent.from_work_item(item, policy)
    second = MutationIntent.from_work_item(item, policy)
    assert first.key == second.key
    assert first.expected_head_sha == SHA_B
    assert first.expected_base_sha == SHA_A


def test_mutation_intent_changes_with_method():
    item = work_item()
    squash = MutationIntent.from_work_item(item, runner_policy())
    merge = MutationIntent.from_work_item(
        item,
        replace(runner_policy(), merge_method="merge"),
    )
    assert squash.key != merge.key


def test_mutation_receipt_applied_property():
    intent = MutationIntent.from_work_item(work_item(), runner_policy())
    result = MutationReceipt(
        intent=intent,
        state=MutationState.APPLIED,
        observed_head_sha=SHA_B,
        observed_base_sha=SHA_A,
        merge_sha="c" * 40,
        message="merged",
        preconditions=None,
        started_at=NOW.isoformat(),
        finished_at=NOW.isoformat(),
    )
    assert result.applied


def test_target_result_validates_counters():
    with pytest.raises(ValueError):
        TargetResult(
            number=42,
            state=WorkState.READY,
            decision=Decision.READY,
            reasons=(),
            snapshot_fingerprint=None,
            mutations=(),
            request_count=-1,
            duration_ms=0,
        )


@pytest.mark.parametrize(
    "states,expected",
    [
        ((CheckState.PASSING,), "passing"),
        ((CheckState.FAILING,), "failing"),
        ((CheckState.CANCELLED,), "failing"),
        ((CheckState.PENDING,), "pending"),
        ((CheckState.MISSING,), "missing"),
        ((CheckState.UNKNOWN,), "unknown"),
        ((CheckState.SKIPPED,), "unknown"),
        ((), "missing"),
    ],
)
def test_ci_state_from_checks(states, expected):
    assert ci_state_from_checks(states).value == expected


def test_snapshot_policy_fingerprint_ignores_capture_time():
    first = snapshot()
    second = replace(
        first,
        captured_at=(NOW + timedelta(minutes=1)).isoformat(),
        source_request_count=99,
    )
    assert snapshot_policy_fingerprint(first) == snapshot_policy_fingerprint(second)


def test_snapshot_policy_fingerprint_covers_author():
    first = snapshot()
    second = replace(first, author="different")
    assert snapshot_policy_fingerprint(first) != snapshot_policy_fingerprint(second)


def test_snapshot_policy_fingerprint_covers_base_head():
    first = snapshot()
    second = replace(first, base_head_sha=SHA_B)
    assert snapshot_policy_fingerprint(first) != snapshot_policy_fingerprint(second)


def test_policy_serializes_to_canonical_json():
    payload = json.loads(canonical_json(asdict(runner_policy())))
    assert payload["merge_method"] == "squash"
    assert payload["mode"] == "apply"
