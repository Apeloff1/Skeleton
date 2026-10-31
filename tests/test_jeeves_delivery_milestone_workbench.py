"""Execute all 100 distinct milestone measurements against source-bound host evidence.

These fixtures exercise acceptance math and independent-evidence contracts.
They are not substitutes for production CI, Godot, rights or GPU execution.
"""

from dataclasses import replace

import pytest

from skeleton.jeeves.agent.delivery_assurance_milestones import MilestoneBoard
from skeleton.jeeves.agent.delivery_milestone_workbench import (
    ACCEPTANCE_CRITERIA, CRITERION_BY_ID, ExecutionVerdict,
    HostMeasurement, WorkbenchError, evaluate_milestone,
    execute_milestone_batch,
)


COMMIT = "b" * 40
ARTIFACT = "c" * 64


def correct_value(spec):
    if spec.comparison == "at_least":
        return spec.target + 1
    return spec.target


def failing_value(spec):
    if spec.comparison == "at_least":
        return spec.target - 1
    if spec.comparison == "at_most":
        return spec.target + 1
    return spec.target + 1


def checker(name, *, value=None, samples=None, unit=None, source=None, digest=None,
            scope="specific identical host fixture", method="fixture-metric-v1"):
    def run(spec, source_commit, artifact_digest):
        return HostMeasurement(
            milestone_id=spec.milestone_id, checker_id=name,
            source_commit=source if source is not None else source_commit,
            artifact_digest=digest if digest is not None else artifact_digest,
            metric=spec.metric,
            unit=spec.unit if unit is None else unit,
            observed=correct_value(spec) if value is None else value,
            sample_count=spec.min_samples if samples is None else samples,
            method=method, evidence_ref=f"host:{name}:{spec.milestone_id}",
            scope=scope,
        )
    return run


def two_checkers(**kwargs):
    return checker("host-primary", **kwargs), checker("host-secondary", **kwargs)


def test_all_hundred_gates_have_unique_measured_objectives():
    assert len(ACCEPTANCE_CRITERIA) == len(CRITERION_BY_ID) == 100
    assert len({x.metric for x in ACCEPTANCE_CRITERIA}) == 100
    assert len({x.milestone_id for x in ACCEPTANCE_CRITERIA}) == 100
    assert set(x.comparison for x in ACCEPTANCE_CRITERIA) == {
        "exact", "at_most", "at_least",
    }
    assert all(x.min_samples >= 1 for x in ACCEPTANCE_CRITERIA)


@pytest.mark.parametrize("criterion", ACCEPTANCE_CRITERIA,
                         ids=lambda item: item.milestone_id)
def test_every_distinct_milestone_executes_its_specific_pass_condition(criterion):
    first, second = two_checkers()
    result = evaluate_milestone(
        criterion.milestone_id, COMMIT, ARTIFACT, first, second,
    )
    assert isinstance(result, ExecutionVerdict)
    assert result.passed
    assert result.attestation.milestone_id == criterion.milestone_id
    assert result.attestation.source_commit == COMMIT
    assert result.attestation.artifact_digest == ARTIFACT
    assert result.primary_digest != result.independent_digest
    assert len(result.fingerprint) == 64


@pytest.mark.parametrize("criterion", ACCEPTANCE_CRITERIA,
                         ids=lambda item: item.milestone_id)
def test_every_distinct_milestone_blocks_its_specific_failed_objective(criterion):
    first, second = two_checkers(value=failing_value(criterion))
    outcome = evaluate_milestone(
        criterion.milestone_id, COMMIT, ARTIFACT, first, second,
    )
    assert not outcome.passed
    assert outcome.attestation is None
    assert "objective" in outcome.detail


@pytest.mark.parametrize("criterion", ACCEPTANCE_CRITERIA,
                         ids=lambda item: item.milestone_id)
def test_all_hundred_milestones_require_actual_minimum_sample_coverage(criterion):
    first, second = two_checkers(samples=max(1, criterion.min_samples - 1))
    outcome = evaluate_milestone(
        criterion.milestone_id, COMMIT, ARTIFACT, first, second,
    )
    if criterion.min_samples > 1:
        assert not outcome.passed
        assert "samples" in outcome.detail


def test_full_hundred_pass_batch_creates_hash_linked_board():
    checkers = {item.milestone_id: two_checkers() for item in ACCEPTANCE_CRITERIA}
    report = execute_milestone_batch(
        MilestoneBoard.begin(COMMIT), ARTIFACT, checkers,
    )
    assert report.board.completion_count == 100
    assert report.board.completion_percent == 100
    assert len(report.attempts) == 100
    assert not report.deferred
    assert report.summary()["target"] == 100
    assert report.summary()["failed"] == 0
    assert len(report.fingerprint) == 64
    for index, receipt in enumerate(report.board.receipts):
        assert receipt.milestone_id == f"M{index + 1:03d}"


def test_missing_all_host_checkers_never_fabricates_any_completion():
    result = execute_milestone_batch(MilestoneBoard.begin(COMMIT), ARTIFACT, {})
    assert result.board.completion_count == 0
    assert len(result.attempts) == 10
    assert len(result.deferred) == 90
    assert result.summary()["unverified"] == 100
    assert all(not entry.passed for entry in result.attempts)
    assert all("host checkers" in entry.detail for entry in result.attempts)


def test_partial_batch_can_resume_without_duplicate_receipts():
    first_half = {
        item.milestone_id: two_checkers()
        for item in ACCEPTANCE_CRITERIA[:50]
    }
    board = MilestoneBoard.begin(COMMIT)
    first = execute_milestone_batch(
        board, ARTIFACT, first_half, requested=tuple(first_half),
    )
    assert first.board.completion_count == 50
    remainder = {
        item.milestone_id: two_checkers()
        for item in ACCEPTANCE_CRITERIA[50:]
    }
    last = execute_milestone_batch(
        first.board, ARTIFACT, remainder,
        requested=tuple(remainder),
    )
    assert last.board.completion_count == 100
    assert len(last.board.receipts) == 100
    replay = execute_milestone_batch(
        last.board, ARTIFACT,
        {item.milestone_id: two_checkers() for item in ACCEPTANCE_CRITERIA},
    )
    assert replay.board == last.board
    assert not replay.attempts


def test_unsatisfied_prerequisite_defers_downstream_candidate():
    result = execute_milestone_batch(
        MilestoneBoard.begin(COMMIT), ARTIFACT,
        {"M002": two_checkers()}, requested=("M002",),
    )
    assert result.deferred == ("M002",)
    assert not result.attempts


def test_failed_dependency_blocks_later_milestones_even_if_they_report_pass():
    bad = CRITERION_BY_ID["M001"]
    report = execute_milestone_batch(
        MilestoneBoard.begin(COMMIT), ARTIFACT,
        {"M001": two_checkers(value=failing_value(bad)),
         "M002": two_checkers()},
        requested=("M001", "M002"),
    )
    assert not report.board.passing
    assert report.deferred == ("M002",)
    assert report.attempts[0].result == "blocked"


@pytest.mark.parametrize("change,reason", (
    ({"source": "d" * 40}, "stale"),
    ({"digest": "e" * 64}, "stale"),
    ({"unit": "wrong"}, "wrong units"),
    ({"samples": 1}, "samples"),
    ({"method": "different-method"}, "methods"),
    ({"scope": "outside scope"}, "scope"),
))
def test_stale_scope_method_samples_and_units_are_not_approvals(change, reason):
    spec = CRITERION_BY_ID["M001"]
    a = checker("host-primary")
    b = checker("host-secondary", **change)
    result = evaluate_milestone("M001", COMMIT, ARTIFACT, a, b)
    assert not result.passed
    assert reason in result.detail


def test_identical_checker_identity_or_evidence_cannot_pass():
    a = checker("host-primary")
    same_identity = checker("host-primary")
    assert not evaluate_milestone(
        "M001", COMMIT, ARTIFACT, a, same_identity,
    ).passed

    def reused_proof(spec, commit, digest):
        return replace(
            checker("host-secondary")(spec, commit, digest),
            evidence_ref=f"host:host-primary:{spec.milestone_id}",
        )
    assert not evaluate_milestone(
        "M001", COMMIT, ARTIFACT, a, reused_proof,
    ).passed


def test_disagreement_is_rejected_even_if_both_individually_meet_target():
    spec = CRITERION_BY_ID["M001"]
    result = evaluate_milestone(
        "M001", COMMIT, ARTIFACT,
        checker("host-primary", value=spec.target),
        checker("host-secondary", value=spec.target + 1),
    )
    assert not result.passed
    assert "disagree" in result.detail


def test_invalid_evidence_ref_and_nonfinite_observations_fail_closed():
    with pytest.raises(WorkbenchError, match="nonfinite"):
        checker("host-primary", value=float("nan"))(
            CRITERION_BY_ID["M001"], COMMIT, ARTIFACT,
        )
    with pytest.raises(WorkbenchError, match="exact source commit"):
        evaluate_milestone("M001", "main", ARTIFACT, *two_checkers())
    with pytest.raises(WorkbenchError, match="source artifact hash"):
        evaluate_milestone("M001", COMMIT, "bad", *two_checkers())
    with pytest.raises(WorkbenchError, match="not executable"):
        evaluate_milestone("M101", COMMIT, ARTIFACT, *two_checkers())


def test_batch_rejects_unknown_milestone_and_changed_source_board():
    with pytest.raises(WorkbenchError, match="unknown"):
        execute_milestone_batch(
            MilestoneBoard.begin(COMMIT), ARTIFACT, {},
            requested=("M101",),
        )
    report = execute_milestone_batch(
        MilestoneBoard.begin(COMMIT), ARTIFACT, {"M001": two_checkers()},
        requested=("M001",),
    )
    assert report.board.source_commit == COMMIT
    assert report.board.register(report.attempts[0].attestation) == report.board
