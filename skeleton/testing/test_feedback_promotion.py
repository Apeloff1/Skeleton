from __future__ import annotations

import pytest

from skeleton.intelligence.feedback_promotion import (
    FeedbackEvent,
    FeedbackPolicy,
    FeedbackPromotionError,
    FeedbackPromotionPipeline,
)


def _seed_significant_experiment(
    pipeline: FeedbackPromotionPipeline,
    *,
    experiment_id: str = "quality-v2",
) -> None:
    counts = {"baseline": 0, "candidate": 0}
    index = 0
    while min(counts.values()) < 12 and index < 500:
        subject_id = f"subject-{index}"
        variant = pipeline.assign(experiment_id, subject_id)
        if counts[variant] < 12:
            value = (
                0.20 + (counts[variant] % 3) * 0.01
                if variant == "baseline"
                else 0.80 + (counts[variant] % 3) * 0.01
            )
            pipeline.record_feedback(
                FeedbackEvent(
                    event_id=f"event-{index}",
                    experiment_id=experiment_id,
                    subject_id=subject_id,
                    variant=variant,
                    metric="quality",
                    value=value,
                    consent=True,
                    data_use="product_improvement",
                    created_at=float(index + 1),
                )
            )
            counts[variant] += 1
        index += 1

    assert counts == {"baseline": 12, "candidate": 12}


def test_feedback_collection_never_mutates_production_before_promotion() -> None:
    pipeline = FeedbackPromotionPipeline()
    pipeline.create_experiment("quality-v2")

    _seed_significant_experiment(pipeline)

    assert pipeline.active_variant("quality-v2") == "baseline"
    receipt = pipeline.evaluate("quality-v2", candidate_variant="candidate")
    assert receipt.significant is True
    assert receipt.eligible is True
    assert receipt.candidate_mean > receipt.baseline_mean
    assert pipeline.active_variant("quality-v2") == "baseline"

    action = pipeline.promote("quality-v2", receipt)
    assert action.action == "promoted"
    assert action.from_variant == "baseline"
    assert action.to_variant == "candidate"
    assert action.evaluation_digest == receipt.evidence_digest
    assert pipeline.active_variant("quality-v2") == "candidate"


def test_promotion_requires_current_eligible_evaluation_receipt() -> None:
    pipeline = FeedbackPromotionPipeline()
    pipeline.create_experiment("quality-v2")

    with pytest.raises(
        FeedbackPromotionError,
        match="promotion requires an evaluation receipt",
    ):
        pipeline.promote("quality-v2", object())  # type: ignore[arg-type]

    subject = "subject-low-evidence"
    variant = pipeline.assign("quality-v2", subject)
    pipeline.record_feedback(
        FeedbackEvent(
            event_id="event-low-evidence",
            experiment_id="quality-v2",
            subject_id=subject,
            variant=variant,
            metric="quality",
            value=0.5,
            consent=True,
            data_use="product_improvement",
            created_at=1.0,
        )
    )
    other = "other-low-evidence"
    other_variant = pipeline.assign("quality-v2", other)
    if other_variant == variant:
        for index in range(100):
            candidate = f"other-{index}"
            other_variant = pipeline.assign("quality-v2", candidate)
            if other_variant != variant:
                other = candidate
                break
    pipeline.record_feedback(
        FeedbackEvent(
            event_id="event-other-low-evidence",
            experiment_id="quality-v2",
            subject_id=other,
            variant=other_variant,
            metric="quality",
            value=0.6,
            consent=True,
            data_use="product_improvement",
            created_at=2.0,
        )
    )

    receipt = pipeline.evaluate("quality-v2", candidate_variant="candidate")
    assert receipt.eligible is False
    with pytest.raises(
        FeedbackPromotionError,
        match="evaluation receipt is not eligible",
    ):
        pipeline.promote("quality-v2", receipt)


def test_feedback_is_bound_to_assignment_consent_and_declared_data_use() -> None:
    pipeline = FeedbackPromotionPipeline(
        FeedbackPolicy(
            allowed_data_uses=("product_improvement",),
            require_consent=True,
        )
    )
    pipeline.create_experiment("quality-v2")
    subject = "subject-a"
    assigned = pipeline.assign("quality-v2", subject)
    wrong = "candidate" if assigned == "baseline" else "baseline"

    with pytest.raises(
        FeedbackPromotionError,
        match="feedback consent is required",
    ):
        pipeline.record_feedback(
            FeedbackEvent(
                event_id="no-consent",
                experiment_id="quality-v2",
                subject_id=subject,
                variant=assigned,
                metric="quality",
                value=0.5,
                consent=False,
                data_use="product_improvement",
                created_at=1.0,
            )
        )

    with pytest.raises(
        FeedbackPromotionError,
        match="data use is not permitted",
    ):
        pipeline.record_feedback(
            FeedbackEvent(
                event_id="wrong-use",
                experiment_id="quality-v2",
                subject_id=subject,
                variant=assigned,
                metric="quality",
                value=0.5,
                consent=True,
                data_use="advertising",
                created_at=1.0,
            )
        )

    with pytest.raises(
        FeedbackPromotionError,
        match="does not match deterministic assignment",
    ):
        pipeline.record_feedback(
            FeedbackEvent(
                event_id="wrong-variant",
                experiment_id="quality-v2",
                subject_id=subject,
                variant=wrong,
                metric="quality",
                value=0.5,
                consent=True,
                data_use="product_improvement",
                created_at=1.0,
            )
        )


def test_duplicate_feedback_is_idempotent_but_conflicts_fail_closed() -> None:
    pipeline = FeedbackPromotionPipeline()
    pipeline.create_experiment("quality-v2")
    subject = "subject-a"
    assigned = pipeline.assign("quality-v2", subject)
    event = FeedbackEvent(
        event_id="event-a",
        experiment_id="quality-v2",
        subject_id=subject,
        variant=assigned,
        metric="quality",
        value=0.5,
        consent=True,
        data_use="product_improvement",
        created_at=1.0,
    )

    assert pipeline.record_feedback(event) == event
    assert pipeline.record_feedback(event) == event

    with pytest.raises(
        FeedbackPromotionError,
        match="feedback event id conflict",
    ):
        pipeline.record_feedback(
            FeedbackEvent(
                event_id="event-a",
                experiment_id="quality-v2",
                subject_id=subject,
                variant=assigned,
                metric="quality",
                value=0.7,
                consent=True,
                data_use="product_improvement",
                created_at=1.0,
            )
        )


def test_promoted_candidate_can_roll_back_to_baseline() -> None:
    clock_values = iter((100.0, 101.0))
    pipeline = FeedbackPromotionPipeline(clock=lambda: next(clock_values))
    pipeline.create_experiment("quality-v2")
    _seed_significant_experiment(pipeline)

    receipt = pipeline.evaluate("quality-v2", candidate_variant="candidate")
    promoted = pipeline.promote("quality-v2", receipt)
    assert promoted.occurred_at == 100.0
    assert pipeline.active_variant("quality-v2") == "candidate"

    rollback = pipeline.rollback(
        "quality-v2",
        reason="post-promotion regression",
    )
    assert rollback.action == "rolled_back"
    assert rollback.from_variant == "candidate"
    assert rollback.to_variant == "baseline"
    assert rollback.occurred_at == 101.0
    assert pipeline.active_variant("quality-v2") == "baseline"
    assert [item.action for item in pipeline.promotion_history("quality-v2")] == [
        "promoted",
        "rolled_back",
    ]
