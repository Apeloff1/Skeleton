from __future__ import annotations

import pytest

from skeleton.ai.learning.promotion import (
    EvaluationReceipt,
    ExperimentAssignment,
    ExperimentSpec,
    FeedbackEvent,
    FeedbackLedger,
    FeedbackPromotionError,
    FeedbackPromotionPipeline,
    PromotionReceipt,
)


def _spec(*, minimum: int = 2) -> ExperimentSpec:
    return ExperimentSpec(
        experiment_id="exp-learning-integrity",
        baseline_version="model-v1",
        candidate_version="model-v2",
        assignment_salt="learning-integrity-v1",
        data_use_purpose="quality-evaluation",
        holdout_bps=1000,
        candidate_bps=4500,
        min_variant_samples=minimum,
    )


def _subjects(
    spec: ExperimentSpec,
    variant: str,
    count: int,
    *,
    start_index: int = 0,
) -> list[str]:
    result: list[str] = []
    index = start_index
    while len(result) < count:
        subject = f"subject-{index}"
        if spec.assignment_for(subject) == variant:
            result.append(subject)
        index += 1
        if index > start_index + 200_000:
            raise AssertionError("unable to find deterministic subject fixture")
    return result


def _collect(
    ledger: FeedbackLedger,
    spec: ExperimentSpec,
    *,
    variant: str,
    count: int,
    observed_at: int,
    prefix: str,
    subject_start: int = 0,
) -> list[FeedbackEvent]:
    events: list[FeedbackEvent] = []
    for offset, subject in enumerate(
        _subjects(spec, variant, count, start_index=subject_start)
    ):
        assignment = ledger.assign(spec, subject)
        events.append(
            ledger.collect(
                spec,
                assignment,
                event_id=f"{prefix}-{variant}-{offset}",
                score=0.9 if variant == "candidate" else 0.7,
                observed_at=observed_at + offset,
                consent=True,
                data_use_purpose=spec.data_use_purpose,
            )
        )
    return events


def _balanced_events(
    ledger: FeedbackLedger,
    spec: ExperimentSpec,
    *,
    baseline_at: int = 100,
    candidate_at: int = 200,
    prefix: str = "initial",
    subject_start: int = 0,
) -> list[FeedbackEvent]:
    return [
        *_collect(
            ledger,
            spec,
            variant="baseline",
            count=spec.min_variant_samples,
            observed_at=baseline_at,
            prefix=prefix,
            subject_start=subject_start,
        ),
        *_collect(
            ledger,
            spec,
            variant="candidate",
            count=spec.min_variant_samples,
            observed_at=candidate_at,
            prefix=prefix,
            subject_start=subject_start,
        ),
    ]


def _evaluation(
    spec: ExperimentSpec,
    events: list[FeedbackEvent],
    *,
    evaluated_at: int,
    evidence_ref: str,
) -> EvaluationReceipt:
    return EvaluationReceipt(
        experiment_id=spec.experiment_id,
        baseline_version=spec.baseline_version,
        candidate_version=spec.candidate_version,
        evaluator_id="independent-evaluator-v1",
        passed=True,
        event_ids=tuple(event.event_id for event in events),
        metric_delta=0.2,
        evaluated_at=evaluated_at,
        evidence_ref=evidence_ref,
    )


def test_assignment_and_feedback_reject_nonhex_spec_digest() -> None:
    spec = _spec()
    with pytest.raises(FeedbackPromotionError, match="lowercase sha256"):
        ExperimentAssignment(
            experiment_id=spec.experiment_id,
            subject_id="subject-x",
            variant="candidate",
            spec_digest="z" * 64,
        )

    with pytest.raises(FeedbackPromotionError, match="lowercase sha256"):
        FeedbackEvent(
            event_id="event-x",
            experiment_id=spec.experiment_id,
            subject_id="subject-x",
            variant="candidate",
            score=0.5,
            observed_at=1,
            consent=True,
            data_use_purpose=spec.data_use_purpose,
            spec_digest="g" * 64,
        )


def test_promotion_rejects_evaluation_that_predates_referenced_feedback() -> None:
    spec = _spec()
    ledger = FeedbackLedger()
    events = _balanced_events(ledger, spec)
    evaluation = _evaluation(
        spec,
        events,
        evaluated_at=150,
        evidence_ref="eval:time-travel",
    )

    with pytest.raises(FeedbackPromotionError, match="predates"):
        FeedbackPromotionPipeline().promote(
            spec,
            events,
            evaluation,
            promoted_at=300,
        )


def test_promotion_rejects_repeated_subject_evidence() -> None:
    spec = _spec()
    ledger = FeedbackLedger()
    events = _balanced_events(ledger, spec)

    repeated_subject = _subjects(spec, "baseline", 1)[0]
    repeated_assignment = ledger.assign(spec, repeated_subject)
    repeated = ledger.collect(
        spec,
        repeated_assignment,
        event_id="duplicate-subject-observation",
        score=0.8,
        observed_at=250,
        consent=True,
        data_use_purpose=spec.data_use_purpose,
    )
    selected = [*events, repeated]
    evaluation = _evaluation(
        spec,
        selected,
        evaluated_at=300,
        evidence_ref="eval:pseudoreplication",
    )

    with pytest.raises(FeedbackPromotionError, match="repeated subject"):
        FeedbackPromotionPipeline().promote(
            spec,
            selected,
            evaluation,
            promoted_at=301,
        )


def test_promotion_timestamp_cannot_precede_evaluation() -> None:
    spec = _spec()
    ledger = FeedbackLedger()
    events = _balanced_events(ledger, spec)
    evaluation = _evaluation(
        spec,
        events,
        evaluated_at=300,
        evidence_ref="eval:causal-order",
    )

    with pytest.raises(FeedbackPromotionError, match="cannot precede evaluation"):
        FeedbackPromotionPipeline().promote(
            spec,
            events,
            evaluation,
            promoted_at=299,
        )


def test_rollback_timestamp_cannot_precede_active_promotion() -> None:
    spec = _spec()
    ledger = FeedbackLedger()
    events = _balanced_events(ledger, spec)
    evaluation = _evaluation(
        spec,
        events,
        evaluated_at=300,
        evidence_ref="eval:rollback-order",
    )
    pipeline = FeedbackPromotionPipeline()
    pipeline.promote(spec, events, evaluation, promoted_at=301)

    with pytest.raises(FeedbackPromotionError, match="cannot precede"):
        pipeline.rollback(
            spec,
            reason="regression",
            rolled_back_at=300,
        )


def test_rollback_blocks_reuse_of_same_evaluation() -> None:
    spec = _spec()
    ledger = FeedbackLedger()
    events = _balanced_events(ledger, spec)
    evaluation = _evaluation(
        spec,
        events,
        evaluated_at=300,
        evidence_ref="eval:initial",
    )
    pipeline = FeedbackPromotionPipeline()
    pipeline.promote(spec, events, evaluation, promoted_at=301)
    pipeline.rollback(spec, reason="regression", rolled_back_at=400)

    with pytest.raises(FeedbackPromotionError, match="fresh evaluation"):
        pipeline.promote(
            spec,
            events,
            evaluation,
            promoted_at=500,
        )


def test_repromotion_requires_feedback_collected_after_rollback() -> None:
    spec = _spec()
    ledger = FeedbackLedger()
    initial = _balanced_events(ledger, spec)
    initial_evaluation = _evaluation(
        spec,
        initial,
        evaluated_at=300,
        evidence_ref="eval:initial",
    )
    pipeline = FeedbackPromotionPipeline()
    pipeline.promote(spec, initial, initial_evaluation, promoted_at=301)
    pipeline.rollback(spec, reason="regression", rolled_back_at=400)

    reevaluated_old_data = _evaluation(
        spec,
        initial,
        evaluated_at=500,
        evidence_ref="eval:old-data-recheck",
    )
    with pytest.raises(FeedbackPromotionError, match="collected after rollback"):
        pipeline.promote(
            spec,
            initial,
            reevaluated_old_data,
            promoted_at=501,
        )

    fresh = _balanced_events(
        ledger,
        spec,
        baseline_at=450,
        candidate_at=500,
        prefix="fresh",
        subject_start=10_000,
    )
    fresh_evaluation = _evaluation(
        spec,
        fresh,
        evaluated_at=600,
        evidence_ref="eval:fresh-after-rollback",
    )
    promoted = pipeline.promote(
        spec,
        fresh,
        fresh_evaluation,
        promoted_at=601,
    )
    assert promoted.to_version == spec.candidate_version
    assert pipeline.active_version(spec) == spec.candidate_version


def test_receipt_chain_digest_is_deterministic_and_tracks_rollback() -> None:
    spec = _spec()
    ledger = FeedbackLedger()
    events = _balanced_events(ledger, spec)
    evaluation = _evaluation(
        spec,
        events,
        evaluated_at=300,
        evidence_ref="eval:chain",
    )
    pipeline = FeedbackPromotionPipeline()
    pipeline.promote(spec, events, evaluation, promoted_at=301)
    first = pipeline.receipt_chain_digest(spec)
    assert first == pipeline.receipt_chain_digest(spec)

    pipeline.rollback(spec, reason="regression", rolled_back_at=400)
    second = pipeline.receipt_chain_digest(spec)
    assert second != first
    pipeline.assert_history_integrity(spec)


def test_promotion_receipt_validates_digest_and_rollback_reason_semantics() -> None:
    with pytest.raises(FeedbackPromotionError, match="lowercase sha256"):
        PromotionReceipt(
            experiment_id="exp",
            from_version="v1",
            to_version="v2",
            evaluation_digest="x" * 64,
            promoted_at=1,
        )

    with pytest.raises(FeedbackPromotionError, match="rollback reason"):
        PromotionReceipt(
            experiment_id="exp",
            from_version="v1",
            to_version="v2",
            evaluation_digest="0" * 64,
            promoted_at=1,
            reason="not allowed",
        )
