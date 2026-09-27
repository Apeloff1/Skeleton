from __future__ import annotations

import pytest

from skeleton.learning.promotion import (
    EvaluationReceipt,
    ExperimentSpec,
    FeedbackLedger,
    FeedbackPromotionError,
    FeedbackPromotionPipeline,
)


def _spec(*, experiment_id: str = "exp-ranking") -> ExperimentSpec:
    return ExperimentSpec(
        experiment_id=experiment_id,
        baseline_version="ranker-v1",
        candidate_version="ranker-v2",
        assignment_salt="stable-assignment-v1",
        data_use_purpose="ranking-quality-evaluation",
        holdout_bps=1000,
        candidate_bps=4500,
        min_variant_samples=2,
    )


def _subjects(spec: ExperimentSpec, variant: str, count: int) -> list[str]:
    result = []
    index = 0
    while len(result) < count:
        subject = f"subject-{index}"
        if spec.assignment_for(subject) == variant:
            result.append(subject)
        index += 1
        if index > 100_000:
            raise AssertionError("unable to find deterministic assignment fixture")
    return result


def _collect(
    ledger: FeedbackLedger,
    spec: ExperimentSpec,
    *,
    variant: str,
    count: int,
    start: int,
):
    events = []
    for offset, subject in enumerate(_subjects(spec, variant, count)):
        assignment = ledger.assign(spec, subject)
        events.append(
            ledger.collect(
                spec,
                assignment,
                event_id=f"{variant}-{offset}",
                score=0.9 if variant == "candidate" else 0.7,
                observed_at=start + offset,
                consent=True,
                data_use_purpose=spec.data_use_purpose,
            )
        )
    return events


def test_assignment_is_deterministic_and_experiment_isolated() -> None:
    first = _spec(experiment_id="exp-a")
    second = _spec(experiment_id="exp-b")
    ledger = FeedbackLedger()

    a1 = ledger.assign(first, "subject-42")
    a2 = ledger.assign(first, "subject-42")
    b = ledger.assign(second, "subject-42")

    assert a1 == a2
    assert a1.spec_digest == first.digest
    assert b.spec_digest == second.digest
    assert first.digest != second.digest


def test_feedback_collection_requires_consent_and_declared_data_use() -> None:
    spec = _spec()
    ledger = FeedbackLedger()
    assignment = ledger.assign(spec, "subject-42")

    with pytest.raises(FeedbackPromotionError, match="explicit consent"):
        ledger.collect(
            spec,
            assignment,
            event_id="event-no-consent",
            score=0.5,
            observed_at=100,
            consent=False,
            data_use_purpose=spec.data_use_purpose,
        )

    with pytest.raises(FeedbackPromotionError, match="data-use purpose"):
        ledger.collect(
            spec,
            assignment,
            event_id="event-wrong-purpose",
            score=0.5,
            observed_at=100,
            consent=True,
            data_use_purpose="unrelated-training",
        )


def test_tampered_assignment_fails_closed() -> None:
    spec = _spec()
    ledger = FeedbackLedger()
    assignment = ledger.assign(spec, "subject-42")
    wrong_variant = (
        "baseline"
        if assignment.variant != "baseline"
        else "candidate"
    )
    tampered = type(assignment)(
        experiment_id=assignment.experiment_id,
        subject_id=assignment.subject_id,
        variant=wrong_variant,
        spec_digest=assignment.spec_digest,
    )

    with pytest.raises(FeedbackPromotionError, match="variant was tampered"):
        ledger.collect(
            spec,
            tampered,
            event_id="tampered",
            score=0.5,
            observed_at=100,
            consent=True,
            data_use_purpose=spec.data_use_purpose,
        )


def test_promotion_requires_passing_eval_and_balanced_variant_evidence() -> None:
    spec = _spec()
    ledger = FeedbackLedger()
    events = [
        *_collect(ledger, spec, variant="baseline", count=2, start=100),
        *_collect(ledger, spec, variant="candidate", count=2, start=200),
    ]
    event_ids = tuple(event.event_id for event in events)
    pipeline = FeedbackPromotionPipeline()

    failed = EvaluationReceipt(
        experiment_id=spec.experiment_id,
        baseline_version=spec.baseline_version,
        candidate_version=spec.candidate_version,
        evaluator_id="independent-eval-v1",
        passed=False,
        event_ids=event_ids,
        metric_delta=0.2,
        evaluated_at=300,
        evidence_ref="eval:ranking:failed",
    )
    with pytest.raises(FeedbackPromotionError, match="passing evaluation"):
        pipeline.promote(spec, events, failed, promoted_at=301)

    passed = EvaluationReceipt(
        experiment_id=spec.experiment_id,
        baseline_version=spec.baseline_version,
        candidate_version=spec.candidate_version,
        evaluator_id="independent-eval-v1",
        passed=True,
        event_ids=event_ids,
        metric_delta=0.2,
        evaluated_at=300,
        evidence_ref="eval:ranking:passed",
    )
    receipt = pipeline.promote(spec, events, passed, promoted_at=301)

    assert pipeline.active_version(spec) == spec.candidate_version
    assert receipt.from_version == spec.baseline_version
    assert receipt.to_version == spec.candidate_version
    assert receipt.evaluation_digest == passed.digest


def test_holdout_feedback_isolated_from_promotion_evaluation() -> None:
    spec = _spec()
    ledger = FeedbackLedger()
    events = [
        *_collect(ledger, spec, variant="baseline", count=2, start=100),
        *_collect(ledger, spec, variant="candidate", count=2, start=200),
        *_collect(ledger, spec, variant="holdout", count=1, start=250),
    ]
    receipt = EvaluationReceipt(
        experiment_id=spec.experiment_id,
        baseline_version=spec.baseline_version,
        candidate_version=spec.candidate_version,
        evaluator_id="independent-eval-v1",
        passed=True,
        event_ids=tuple(event.event_id for event in events),
        metric_delta=0.2,
        evaluated_at=300,
        evidence_ref="eval:holdout-leak",
    )

    with pytest.raises(
        FeedbackPromotionError,
        match="holdout feedback cannot enter",
    ):
        FeedbackPromotionPipeline().promote(
            spec,
            events,
            receipt,
            promoted_at=301,
        )


def test_positive_eval_still_requires_minimum_variant_samples() -> None:
    spec = _spec()
    ledger = FeedbackLedger()
    events = [
        *_collect(ledger, spec, variant="baseline", count=2, start=100),
        *_collect(ledger, spec, variant="candidate", count=1, start=200),
    ]
    receipt = EvaluationReceipt(
        experiment_id=spec.experiment_id,
        baseline_version=spec.baseline_version,
        candidate_version=spec.candidate_version,
        evaluator_id="independent-eval-v1",
        passed=True,
        event_ids=tuple(event.event_id for event in events),
        metric_delta=0.2,
        evaluated_at=300,
        evidence_ref="eval:undersampled",
    )

    with pytest.raises(
        FeedbackPromotionError,
        match="minimum variant sample",
    ):
        FeedbackPromotionPipeline().promote(
            spec,
            events,
            receipt,
            promoted_at=301,
        )


def test_rollback_restores_baseline_with_promotion_lineage() -> None:
    spec = _spec()
    ledger = FeedbackLedger()
    events = [
        *_collect(ledger, spec, variant="baseline", count=2, start=100),
        *_collect(ledger, spec, variant="candidate", count=2, start=200),
    ]
    evaluation = EvaluationReceipt(
        experiment_id=spec.experiment_id,
        baseline_version=spec.baseline_version,
        candidate_version=spec.candidate_version,
        evaluator_id="independent-eval-v1",
        passed=True,
        event_ids=tuple(event.event_id for event in events),
        metric_delta=0.15,
        evaluated_at=300,
        evidence_ref="eval:ranking:passed",
    )
    pipeline = FeedbackPromotionPipeline()
    promoted = pipeline.promote(
        spec,
        events,
        evaluation,
        promoted_at=301,
    )

    rollback = pipeline.rollback(
        spec,
        reason="post-promotion regression",
        rolled_back_at=400,
    )

    assert rollback.rollback is True
    assert rollback.from_version == spec.candidate_version
    assert rollback.to_version == spec.baseline_version
    assert rollback.evaluation_digest == promoted.evaluation_digest
    assert pipeline.active_version(spec) == spec.baseline_version
    assert pipeline.receipts(spec.experiment_id) == (promoted, rollback)


def test_feedback_event_id_is_idempotent_but_conflicting_reuse_is_rejected() -> None:
    spec = _spec()
    ledger = FeedbackLedger()
    subject = _subjects(spec, "candidate", 1)[0]
    assignment = ledger.assign(spec, subject)

    first = ledger.collect(
        spec,
        assignment,
        event_id="event-1",
        score=0.9,
        observed_at=100,
        consent=True,
        data_use_purpose=spec.data_use_purpose,
    )
    replay = ledger.collect(
        spec,
        assignment,
        event_id="event-1",
        score=0.9,
        observed_at=100,
        consent=True,
        data_use_purpose=spec.data_use_purpose,
    )
    assert replay == first

    with pytest.raises(
        FeedbackPromotionError,
        match="reused with different content",
    ):
        ledger.collect(
            spec,
            assignment,
            event_id="event-1",
            score=0.1,
            observed_at=100,
            consent=True,
            data_use_purpose=spec.data_use_purpose,
        )
