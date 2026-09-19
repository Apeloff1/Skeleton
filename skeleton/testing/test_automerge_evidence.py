"""Exact-head evidence aggregation regressions for auto-merge."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from skeleton.pr_automation.automerge_evidence import (
    aggregate_required_workflows,
    duplicate_attempts,
    evidence_complete,
    explain_gate_results,
    latest_exact_head_runs,
    latest_reviews_by_user,
    newest_success_timestamp,
    required_names,
    stability_elapsed,
    stale_successes,
    summarize_evidence,
    summarize_reviews,
    workflow_state_counts,
)
from skeleton.pr_automation.automerge_model import (
    GateRequirement,
    GateState,
    ReviewEvidence,
)
from skeleton.testing.automerge_test_support import (
    BASE_WORKFLOWS,
    NOW,
    SHA_A,
    SHA_B,
    reviews,
    successful_runs,
    workflow,
)


def test_latest_exact_head_runs_ignores_other_heads():
    runs = (
        workflow("CI/CD", head_sha=SHA_A, run_id=1, run_number=999),
        workflow("CI/CD", head_sha=SHA_B, run_id=2, run_number=1),
    )
    latest = latest_exact_head_runs(runs, head_sha=SHA_B)
    assert latest["CI/CD"].run_id == 2


def test_latest_exact_head_runs_ignores_push_event_by_default():
    runs = (
        workflow(
            "CI/CD",
            head_sha=SHA_B,
            run_id=1,
            run_number=10,
            event="push",
        ),
        workflow(
            "CI/CD",
            head_sha=SHA_B,
            run_id=2,
            run_number=9,
            event="pull_request",
        ),
    )
    latest = latest_exact_head_runs(runs, head_sha=SHA_B)
    assert latest["CI/CD"].run_id == 2


def test_latest_exact_head_runs_can_include_any_event():
    runs = (
        workflow(
            "CI/CD",
            head_sha=SHA_B,
            run_id=1,
            run_number=10,
            event="push",
        ),
        workflow(
            "CI/CD",
            head_sha=SHA_B,
            run_id=2,
            run_number=9,
            event="pull_request",
        ),
    )
    latest = latest_exact_head_runs(runs, head_sha=SHA_B, event=None)
    assert latest["CI/CD"].run_id == 1


def test_latest_exact_head_runs_prefers_newer_run_number():
    runs = (
        workflow("CI/CD", run_id=1, run_number=10, attempt=1),
        workflow("CI/CD", run_id=2, run_number=11, attempt=1),
    )
    assert latest_exact_head_runs(runs, head_sha=SHA_B)["CI/CD"].run_id == 2


def test_latest_exact_head_runs_prefers_newer_attempt_same_run():
    runs = (
        workflow("CI/CD", run_id=1, run_number=10, attempt=1),
        workflow("CI/CD", run_id=2, run_number=10, attempt=2),
    )
    assert latest_exact_head_runs(runs, head_sha=SHA_B)["CI/CD"].run_id == 2


def test_latest_exact_head_runs_prefers_later_timestamp_tie():
    runs = (
        workflow(
            "CI/CD",
            run_id=1,
            run_number=10,
            attempt=1,
            updated_at=NOW - timedelta(minutes=20),
        ),
        workflow(
            "CI/CD",
            run_id=2,
            run_number=10,
            attempt=1,
            updated_at=NOW - timedelta(minutes=10),
        ),
    )
    assert latest_exact_head_runs(runs, head_sha=SHA_B)["CI/CD"].run_id == 2


def test_missing_required_workflow_is_explicit():
    result = aggregate_required_workflows(
        (),
        (GateRequirement("CI/CD"),),
        head_sha=SHA_B,
    )
    assert len(result) == 1
    assert result[0].state is GateState.MISSING
    assert result[0].run_id is None


@pytest.mark.parametrize(
    "status,conclusion,expected",
    [
        ("completed", "success", GateState.SUCCESS),
        ("queued", None, GateState.PENDING),
        ("in_progress", None, GateState.PENDING),
        ("completed", "failure", GateState.FAILURE),
        ("completed", "timed_out", GateState.FAILURE),
        ("completed", "cancelled", GateState.CANCELLED),
        ("completed", "skipped", GateState.SKIPPED),
        ("completed", "neutral", GateState.UNKNOWN),
    ],
)
def test_required_workflow_state_mapping(status, conclusion, expected):
    result = aggregate_required_workflows(
        (workflow("CI/CD", status=status, conclusion=conclusion),),
        (GateRequirement("CI/CD"),),
        head_sha=SHA_B,
    )
    assert result[0].state is expected


def test_skipped_gate_requires_explicit_allowance():
    run = workflow("Optional Gate", status="completed", conclusion="skipped")
    strict = aggregate_required_workflows(
        (run,),
        (GateRequirement("Optional Gate"),),
        head_sha=SHA_B,
    )
    permissive = aggregate_required_workflows(
        (run,),
        (GateRequirement("Optional Gate", allow_skipped=True),),
        head_sha=SHA_B,
    )
    assert strict[0].state is GateState.SKIPPED
    assert permissive[0].state is GateState.SUCCESS


def test_requirement_can_allow_push_event():
    run = workflow("Main Verification", event="push")
    strict = aggregate_required_workflows(
        (run,),
        (GateRequirement("Main Verification"),),
        head_sha=SHA_B,
    )
    any_event = aggregate_required_workflows(
        (run,),
        (
            GateRequirement(
                "Main Verification",
                require_pull_request_event=False,
            ),
        ),
        head_sha=SHA_B,
    )
    assert strict[0].state is GateState.MISSING
    assert any_event[0].state is GateState.SUCCESS


def test_failed_new_attempt_overrides_old_success():
    runs = (
        workflow("CI/CD", run_id=1, run_number=10, conclusion="success"),
        workflow("CI/CD", run_id=2, run_number=11, conclusion="failure"),
    )
    result = aggregate_required_workflows(
        runs,
        (GateRequirement("CI/CD"),),
        head_sha=SHA_B,
    )
    assert result[0].state is GateState.FAILURE


def test_pending_new_attempt_overrides_old_success():
    runs = (
        workflow("CI/CD", run_id=1, run_number=10, conclusion="success"),
        workflow(
            "CI/CD",
            run_id=2,
            run_number=11,
            status="in_progress",
            conclusion=None,
        ),
    )
    result = aggregate_required_workflows(
        runs,
        (GateRequirement("CI/CD"),),
        head_sha=SHA_B,
    )
    assert result[0].state is GateState.PENDING


def test_cancelled_new_attempt_overrides_old_success():
    runs = (
        workflow("CI/CD", run_id=1, run_number=10, conclusion="success"),
        workflow("CI/CD", run_id=2, run_number=11, conclusion="cancelled"),
    )
    result = aggregate_required_workflows(
        runs,
        (GateRequirement("CI/CD"),),
        head_sha=SHA_B,
    )
    assert result[0].state is GateState.CANCELLED


def test_old_head_success_never_satisfies_new_head():
    runs = successful_runs(BASE_WORKFLOWS, head_sha=SHA_A)
    result = aggregate_required_workflows(
        runs,
        tuple(GateRequirement(name) for name in BASE_WORKFLOWS),
        head_sha=SHA_B,
    )
    assert all(item.state is GateState.MISSING for item in result)


def test_review_latest_state_wins_per_user():
    items = (
        ReviewEvidence(
            login="alice",
            state="APPROVED",
            submitted_at=(NOW - timedelta(minutes=20)).isoformat(),
        ),
        ReviewEvidence(
            login="alice",
            state="CHANGES_REQUESTED",
            submitted_at=(NOW - timedelta(minutes=10)).isoformat(),
        ),
    )
    latest = latest_reviews_by_user(items)
    assert latest["alice"].normalized_state() == "CHANGES_REQUESTED"


def test_review_comment_does_not_override_decisive_review():
    items = (
        ReviewEvidence(
            login="alice",
            state="APPROVED",
            submitted_at=(NOW - timedelta(minutes=20)).isoformat(),
        ),
        ReviewEvidence(
            login="alice",
            state="COMMENTED",
            submitted_at=(NOW - timedelta(minutes=1)).isoformat(),
        ),
    )
    latest = latest_reviews_by_user(items)
    assert latest["alice"].normalized_state() == "APPROVED"


def test_review_logins_are_casefolded():
    items = (
        ReviewEvidence(
            login="Alice",
            state="APPROVED",
            submitted_at=(NOW - timedelta(minutes=20)).isoformat(),
        ),
        ReviewEvidence(
            login="ALICE",
            state="CHANGES_REQUESTED",
            submitted_at=(NOW - timedelta(minutes=10)).isoformat(),
        ),
    )
    latest = latest_reviews_by_user(items)
    assert set(latest) == {"alice"}
    assert latest["alice"].normalized_state() == "CHANGES_REQUESTED"


def test_review_with_timestamp_beats_review_without_timestamp():
    items = (
        ReviewEvidence(login="alice", state="CHANGES_REQUESTED"),
        ReviewEvidence(
            login="alice",
            state="APPROVED",
            submitted_at=NOW.isoformat(),
        ),
    )
    latest = latest_reviews_by_user(items)
    assert latest["alice"].normalized_state() == "APPROVED"


def test_last_review_wins_when_both_timestamps_missing():
    items = (
        ReviewEvidence(login="alice", state="CHANGES_REQUESTED"),
        ReviewEvidence(login="alice", state="APPROVED"),
    )
    latest = latest_reviews_by_user(items)
    assert latest["alice"].normalized_state() == "APPROVED"


def test_summarize_reviews_counts_latest_states():
    summary = summarize_reviews(
        (
            *reviews(approvals=2, changes_requested=1),
            ReviewEvidence(
                login="approver-0",
                state="CHANGES_REQUESTED",
                submitted_at=NOW.isoformat(),
            ),
        )
    )
    assert summary.approvals == 1
    assert summary.changes_requested == 2


def test_evidence_summary_all_successful():
    summary = summarize_evidence(
        runs=successful_runs(),
        requirements=tuple(GateRequirement(name) for name in BASE_WORKFLOWS),
        head_sha=SHA_B,
        reviews=reviews(approvals=1),
        unresolved_threads=0,
    )
    assert summary.all_required_successful
    assert not summary.pending
    assert not summary.missing
    assert not summary.failed


def test_evidence_summary_pending_flag():
    runs = (
        *successful_runs(BASE_WORKFLOWS[:-1]),
        workflow(
            BASE_WORKFLOWS[-1],
            run_id=999,
            run_number=999,
            status="queued",
            conclusion=None,
        ),
    )
    summary = summarize_evidence(
        runs=runs,
        requirements=tuple(GateRequirement(name) for name in BASE_WORKFLOWS),
        head_sha=SHA_B,
        reviews=(),
        unresolved_threads=0,
    )
    assert summary.pending
    assert not summary.all_required_successful


def test_evidence_summary_missing_flag():
    summary = summarize_evidence(
        runs=(),
        requirements=(GateRequirement("CI/CD"),),
        head_sha=SHA_B,
        reviews=(),
        unresolved_threads=0,
    )
    assert summary.missing


@pytest.mark.parametrize(
    "conclusion",
    ["failure", "cancelled", "neutral"],
)
def test_evidence_summary_failed_flag(conclusion):
    summary = summarize_evidence(
        runs=(workflow("CI/CD", conclusion=conclusion),),
        requirements=(GateRequirement("CI/CD"),),
        head_sha=SHA_B,
        reviews=(),
        unresolved_threads=0,
    )
    assert summary.failed


def test_evidence_complete_requires_approvals():
    summary = summarize_evidence(
        runs=successful_runs(),
        requirements=tuple(GateRequirement(name) for name in BASE_WORKFLOWS),
        head_sha=SHA_B,
        reviews=(),
        unresolved_threads=0,
    )
    ready, reasons = evidence_complete(
        summary,
        required_approvals=1,
        require_no_changes_requested=True,
        require_resolved_threads=True,
    )
    assert not ready
    assert "approvals:0:required:1" in reasons


def test_evidence_complete_blocks_change_request():
    summary = summarize_evidence(
        runs=successful_runs(),
        requirements=tuple(GateRequirement(name) for name in BASE_WORKFLOWS),
        head_sha=SHA_B,
        reviews=reviews(changes_requested=1),
        unresolved_threads=0,
    )
    ready, reasons = evidence_complete(
        summary,
        required_approvals=0,
        require_no_changes_requested=True,
        require_resolved_threads=True,
    )
    assert not ready
    assert "changes_requested:1" in reasons


def test_evidence_complete_can_ignore_change_requests_by_policy():
    summary = summarize_evidence(
        runs=successful_runs(),
        requirements=tuple(GateRequirement(name) for name in BASE_WORKFLOWS),
        head_sha=SHA_B,
        reviews=reviews(changes_requested=1),
        unresolved_threads=0,
    )
    ready, reasons = evidence_complete(
        summary,
        required_approvals=0,
        require_no_changes_requested=False,
        require_resolved_threads=True,
    )
    assert ready
    assert reasons == ()


def test_evidence_complete_requires_known_review_threads():
    summary = summarize_evidence(
        runs=successful_runs(),
        requirements=tuple(GateRequirement(name) for name in BASE_WORKFLOWS),
        head_sha=SHA_B,
        reviews=(),
        unresolved_threads=None,
    )
    ready, reasons = evidence_complete(
        summary,
        required_approvals=0,
        require_no_changes_requested=True,
        require_resolved_threads=True,
    )
    assert not ready
    assert "review_threads:unknown" in reasons


def test_evidence_complete_blocks_unresolved_threads():
    summary = summarize_evidence(
        runs=successful_runs(),
        requirements=tuple(GateRequirement(name) for name in BASE_WORKFLOWS),
        head_sha=SHA_B,
        reviews=(),
        unresolved_threads=3,
    )
    ready, reasons = evidence_complete(
        summary,
        required_approvals=0,
        require_no_changes_requested=True,
        require_resolved_threads=True,
    )
    assert not ready
    assert "review_threads:unresolved:3" in reasons


def test_evidence_complete_can_ignore_threads_by_policy():
    summary = summarize_evidence(
        runs=successful_runs(),
        requirements=tuple(GateRequirement(name) for name in BASE_WORKFLOWS),
        head_sha=SHA_B,
        reviews=(),
        unresolved_threads=None,
    )
    ready, reasons = evidence_complete(
        summary,
        required_approvals=0,
        require_no_changes_requested=True,
        require_resolved_threads=False,
    )
    assert ready
    assert reasons == ()


def test_evidence_complete_reports_all_bad_gates():
    runs = (
        workflow("A", conclusion="failure"),
        workflow("B", status="queued", conclusion=None),
    )
    summary = summarize_evidence(
        runs=runs,
        requirements=(
            GateRequirement("A"),
            GateRequirement("B"),
            GateRequirement("C"),
        ),
        head_sha=SHA_B,
        reviews=(),
        unresolved_threads=0,
    )
    ready, reasons = evidence_complete(
        summary,
        required_approvals=0,
        require_no_changes_requested=True,
        require_resolved_threads=True,
    )
    assert not ready
    assert "gate:A:failure" in reasons
    assert "gate:B:pending" in reasons
    assert "gate:C:missing" in reasons


def test_explain_gate_results_is_human_readable():
    gates = aggregate_required_workflows(
        (workflow("CI/CD"),),
        (GateRequirement("CI/CD"),),
        head_sha=SHA_B,
    )
    explained = explain_gate_results(gates)
    assert explained[0].startswith("CI/CD=success")
    assert "exact-head" in explained[0]


def test_required_names_preserves_order():
    reqs = (
        GateRequirement("B"),
        GateRequirement("A"),
        GateRequirement("C"),
    )
    assert required_names(reqs) == ("B", "A", "C")


def test_stale_successes_surfaces_previous_head_only():
    runs = (
        workflow("CI/CD", head_sha=SHA_A, run_id=1, run_number=1),
        workflow("CI/CD", head_sha=SHA_B, run_id=2, run_number=2),
        workflow("Other", head_sha=SHA_A, run_id=3, run_number=3),
    )
    stale = stale_successes(
        runs,
        required_names=("CI/CD",),
        head_sha=SHA_B,
    )
    assert len(stale) == 1
    assert stale[0].head_sha == SHA_A


def test_stale_failures_are_not_reported_as_stale_successes():
    stale = stale_successes(
        (
            workflow(
                "CI/CD",
                head_sha=SHA_A,
                conclusion="failure",
            ),
        ),
        required_names=("CI/CD",),
        head_sha=SHA_B,
    )
    assert stale == ()


def test_duplicate_attempts_returns_multi_run_groups_only():
    runs = (
        workflow("CI/CD", run_id=1, run_number=1),
        workflow("CI/CD", run_id=2, run_number=2),
        workflow("Other", run_id=3, run_number=1),
    )
    duplicates = duplicate_attempts(runs, head_sha=SHA_B)
    assert set(duplicates) == {"CI/CD"}
    assert [item.run_id for item in duplicates["CI/CD"]] == [1, 2]


def test_duplicate_attempts_ignores_other_heads():
    runs = (
        workflow("CI/CD", head_sha=SHA_A, run_id=1, run_number=1),
        workflow("CI/CD", head_sha=SHA_B, run_id=2, run_number=2),
    )
    assert duplicate_attempts(runs, head_sha=SHA_B) == {}


def test_workflow_state_counts_uses_latest_attempt_only():
    runs = (
        workflow("CI/CD", run_id=1, run_number=1, conclusion="failure"),
        workflow("CI/CD", run_id=2, run_number=2, conclusion="success"),
        workflow("Other", run_id=3, run_number=1, status="queued", conclusion=None),
    )
    counts = workflow_state_counts(runs, head_sha=SHA_B)
    assert counts[GateState.SUCCESS] == 1
    assert counts[GateState.PENDING] == 1
    assert counts[GateState.FAILURE] == 0


def test_newest_success_timestamp_requires_every_named_gate():
    runs = successful_runs(("A", "B"))
    assert (
        newest_success_timestamp(
            runs,
            head_sha=SHA_B,
            required_names=("A", "B", "C"),
        )
        is None
    )


def test_newest_success_timestamp_is_maximum_gate_time():
    early = NOW - timedelta(minutes=10)
    late = NOW - timedelta(minutes=2)
    runs = (
        workflow("A", run_id=1, run_number=1, updated_at=early),
        workflow("B", run_id=2, run_number=2, updated_at=late),
    )
    assert newest_success_timestamp(
        runs,
        head_sha=SHA_B,
        required_names=("A", "B"),
    ) == late


def test_stability_elapsed_true_after_window():
    completed = NOW - timedelta(seconds=31)
    runs = (
        workflow("A", updated_at=completed),
        workflow("B", run_id=2, run_number=2, updated_at=completed),
    )
    assert stability_elapsed(
        runs,
        head_sha=SHA_B,
        required_names=("A", "B"),
        now=NOW,
        stability_seconds=30,
    )


def test_stability_elapsed_false_inside_window():
    completed = NOW - timedelta(seconds=29)
    runs = (
        workflow("A", updated_at=completed),
        workflow("B", run_id=2, run_number=2, updated_at=completed),
    )
    assert not stability_elapsed(
        runs,
        head_sha=SHA_B,
        required_names=("A", "B"),
        now=NOW,
        stability_seconds=30,
    )


def test_stability_elapsed_false_when_required_gate_pending():
    runs = (
        workflow("A", updated_at=NOW - timedelta(minutes=5)),
        workflow(
            "B",
            run_id=2,
            run_number=2,
            status="queued",
            conclusion=None,
            updated_at=NOW - timedelta(minutes=5),
        ),
    )
    assert not stability_elapsed(
        runs,
        head_sha=SHA_B,
        required_names=("A", "B"),
        now=NOW,
        stability_seconds=0,
    )


def test_stability_elapsed_supports_naive_now_as_utc():
    completed = NOW - timedelta(minutes=5)
    runs = (workflow("A", updated_at=completed),)
    assert stability_elapsed(
        runs,
        head_sha=SHA_B,
        required_names=("A",),
        now=NOW.replace(tzinfo=None),
        stability_seconds=1,
    )


def test_full_baseline_evidence_matrix_is_complete():
    requirements = tuple(GateRequirement(name) for name in BASE_WORKFLOWS)
    summary = summarize_evidence(
        runs=successful_runs(BASE_WORKFLOWS),
        requirements=requirements,
        head_sha=SHA_B,
        reviews=(),
        unresolved_threads=0,
    )
    ready, reasons = evidence_complete(
        summary,
        required_approvals=0,
        require_no_changes_requested=True,
        require_resolved_threads=True,
    )
    assert ready
    assert reasons == ()
    assert len(summary.gates) == len(BASE_WORKFLOWS)


@pytest.mark.parametrize("missing_name", BASE_WORKFLOWS)
def test_each_baseline_gate_is_independently_required(missing_name):
    names = tuple(name for name in BASE_WORKFLOWS if name != missing_name)
    summary = summarize_evidence(
        runs=successful_runs(names),
        requirements=tuple(GateRequirement(name) for name in BASE_WORKFLOWS),
        head_sha=SHA_B,
        reviews=(),
        unresolved_threads=0,
    )
    ready, reasons = evidence_complete(
        summary,
        required_approvals=0,
        require_no_changes_requested=True,
        require_resolved_threads=True,
    )
    assert not ready
    assert f"gate:{missing_name}:missing" in reasons
