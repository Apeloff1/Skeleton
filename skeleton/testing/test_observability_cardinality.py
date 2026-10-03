from __future__ import annotations

import pytest

from skeleton.ai.runtime.observability.cardinality_control import (
    CardinalityBudget,
    CardinalityControlError,
    CardinalityDecision,
    SamplingPolicy,
    TelemetryLabel,
    assess_cardinality,
)


def _budget(**overrides):
    data = dict(
        metric_id="assistant.requests",
        max_series=1_000,
        per_label_soft_limit=100,
        high_cardinality_exceptions=(),
    )
    data.update(overrides)
    return CardinalityBudget(**data)


def _sampling(**overrides):
    data = dict(
        metric_id="assistant.requests",
        sample_rate_ppm=100_000,
        max_events_per_window=10_000,
    )
    data.update(overrides)
    return SamplingPolicy(**data)


def test_bounded_label_schema_within_budget_is_accepted() -> None:
    labels = (
        TelemetryLabel("region", "bounded", 5),
        TelemetryLabel("model", "bounded", 10),
        TelemetryLabel("tenant_bucket", "system_id", 10),
    )

    decision = assess_cardinality(
        budget=_budget(),
        labels=labels,
        sampling_policy=_sampling(),
    )

    assert decision.accepted is True
    assert decision.projected_max_series == 500
    assert decision.reasons == ()
    assert decision.sampling_override is False
    assert len(decision.digest) == 64


@pytest.mark.parametrize("kind", ("secret", "user_content"))
def test_secret_and_user_content_dimensions_are_rejected(kind: str) -> None:
    with pytest.raises(
        CardinalityControlError,
        match="secret or user-content telemetry dimensions are forbidden",
    ):
        TelemetryLabel(
            name="unsafe",
            source_kind=kind,
            max_distinct_values=10,
        )


def test_high_cardinality_label_requires_declared_exception() -> None:
    label = TelemetryLabel(
        name="request_family",
        source_kind="system_id",
        max_distinct_values=500,
        exception_reason="bounded generated family ID",
    )

    decision = assess_cardinality(
        budget=_budget(),
        labels=(label,),
        sampling_policy=_sampling(),
    )

    assert decision.accepted is False
    assert decision.reasons == ("high-cardinality-label:request_family",)


def test_high_cardinality_exception_requires_reason() -> None:
    label = TelemetryLabel(
        name="request_family",
        source_kind="system_id",
        max_distinct_values=500,
    )

    decision = assess_cardinality(
        budget=_budget(
            high_cardinality_exceptions=("request_family",),
        ),
        labels=(label,),
        sampling_policy=_sampling(),
    )

    assert decision.accepted is False
    assert decision.reasons == (
        "missing-exception-reason:request_family",
    )


def test_declared_exception_does_not_override_global_series_budget() -> None:
    labels = (
        TelemetryLabel(
            "request_family",
            "system_id",
            500,
            exception_reason="bounded generated family ID",
        ),
        TelemetryLabel("region", "bounded", 5),
    )

    decision = assess_cardinality(
        budget=_budget(
            max_series=1_000,
            high_cardinality_exceptions=("request_family",),
        ),
        labels=labels,
        sampling_policy=_sampling(sample_rate_ppm=1),
    )

    assert decision.accepted is False
    assert decision.projected_max_series == 2_500
    assert decision.reasons == ("projected-series-exceeds-budget",)
    assert decision.sampling_override is False


def test_sampling_cannot_rescue_over_cardinality_schema() -> None:
    label = TelemetryLabel(
        "request_family",
        "system_id",
        2_000,
        exception_reason="bounded generated family ID",
    )

    full = assess_cardinality(
        budget=_budget(
            max_series=1_000,
            high_cardinality_exceptions=("request_family",),
        ),
        labels=(label,),
        sampling_policy=_sampling(sample_rate_ppm=1_000_000),
    )
    tiny = assess_cardinality(
        budget=_budget(
            max_series=1_000,
            high_cardinality_exceptions=("request_family",),
        ),
        labels=(label,),
        sampling_policy=_sampling(sample_rate_ppm=1),
    )

    assert full.accepted is False
    assert tiny.accepted is False
    assert full.reasons == tiny.reasons == (
        "projected-series-exceeds-budget",
    )


def test_duplicate_label_names_fail_closed() -> None:
    label = TelemetryLabel("region", "bounded", 5)

    with pytest.raises(
        CardinalityControlError,
        match="label names must be unique",
    ):
        assess_cardinality(
            budget=_budget(),
            labels=(label, label),
            sampling_policy=_sampling(),
        )


def test_sampling_policy_must_match_metric() -> None:
    with pytest.raises(
        CardinalityControlError,
        match="different metric",
    ):
        assess_cardinality(
            budget=_budget(),
            labels=(TelemetryLabel("region", "bounded", 5),),
            sampling_policy=_sampling(metric_id="other.metric"),
        )


def test_sampling_policy_rejects_invalid_ppm() -> None:
    with pytest.raises(
        CardinalityControlError,
        match=r"within \[0, 1000000\]",
    ):
        _sampling(sample_rate_ppm=1_000_001)


def test_decision_cannot_claim_sampling_override() -> None:
    with pytest.raises(
        CardinalityControlError,
        match="sampling cannot override cardinality policy",
    ):
        CardinalityDecision(
            budget_digest="a" * 64,
            sampling_policy_digest="b" * 64,
            projected_max_series=1,
            accepted=True,
            reasons=(),
            sampling_override=True,
        )


def test_label_and_budget_evidence_is_order_stable() -> None:
    left = TelemetryLabel("region", "bounded", 5)
    right = TelemetryLabel("model", "bounded", 10)

    first = assess_cardinality(
        budget=_budget(),
        labels=(left, right),
        sampling_policy=_sampling(),
    )
    second = assess_cardinality(
        budget=_budget(),
        labels=(right, left),
        sampling_policy=_sampling(),
    )

    assert first.projected_max_series == second.projected_max_series
    assert first.accepted == second.accepted
    assert first.reasons == second.reasons


@pytest.mark.parametrize(
    "name",
    (
        "authorization",
        "api-key",
        "refresh_token",
        "user_prompt",
        "raw_content",
    ),
)
def test_sensitive_looking_label_names_are_rejected_even_if_mislabeled(
    name: str,
) -> None:
    with pytest.raises(
        CardinalityControlError,
        match="sensitive-looking telemetry label names are forbidden",
    ):
        TelemetryLabel(
            name=name,
            source_kind="bounded",
            max_distinct_values=10,
        )
