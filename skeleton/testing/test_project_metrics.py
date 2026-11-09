from __future__ import annotations

import hashlib
import math

import pytest

from skeleton.observability import project_metrics as compatibility
from skeleton.contracts import project_metrics as canonical
from skeleton.contracts.project_metrics import (
    MetricClass,
    MetricDefinition,
    MetricError,
    MetricFreshness,
    MetricObservation,
    MetricRegistry,
    ProjectMetric,
)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def definition(
    *,
    metric_id: str = "METRIC.TEST",
    metric_class: MetricClass = MetricClass.QUALITY,
    unit: str = "ratio",
    source_kind: str = "signed-evidence",
    owner_id: str = "OWNER.METRICS",
    max_age_ticks: int = 10,
) -> MetricDefinition:
    return MetricDefinition(
        metric_id=metric_id,
        metric_class=metric_class,
        unit=unit,
        source_kind=source_kind,
        owner_id=owner_id,
        description="project diagnostic metric",
        max_age_ticks=max_age_ticks,
    )


def observation(
    *,
    metric_id: str = "METRIC.TEST",
    value: float = 0.9,
    numerator: int = 9,
    denominator: int = 10,
    source_digest: str | None = None,
    observed_tick: int = 5,
    definition_digest: str | None = None,
    source_kind: str | None = None,
    source_id: str | None = "SOURCE.CI",
    producer_id: str | None = "PRODUCER.METRICS",
    complete: bool = True,
) -> MetricObservation:
    return MetricObservation(
        metric_id=metric_id,
        value=value,
        numerator=numerator,
        denominator=denominator,
        source_digest=source_digest or sha("artifact"),
        observed_tick=observed_tick,
        definition_digest=definition_digest,
        source_kind=source_kind,
        source_id=source_id,
        producer_id=producer_id,
        complete=complete,
    )


def test_observability_surface_has_no_parallel_authority() -> None:
    assert compatibility.__all__ == canonical.__all__
    for name in canonical.__all__:
        assert getattr(compatibility, name) is getattr(canonical, name)


def test_metric_is_bound_to_authoritative_source_digest() -> None:
    metric = MetricRegistry((definition(),)).observe(observation())
    assert metric.observation.source_digest == sha("artifact")
    assert metric.observation.definition_digest == metric.definition.digest
    assert metric.observation.source_kind == "signed-evidence"
    assert metric.observation.bound is True


def test_activity_throughput_quality_risk_and_outcome_classes_remain_distinct() -> None:
    classes = {
        definition(metric_class=metric_class).metric_class
        for metric_class in MetricClass
    }
    assert classes == set(MetricClass)


def test_metrics_cannot_be_declared_completion_authority() -> None:
    with pytest.raises(MetricError, match="completion authority"):
        MetricDefinition(
            "METRIC.X",
            MetricClass.OUTCOME,
            "count",
            "events",
            True,
        )


def test_completion_authority_flag_is_strict_boolean() -> None:
    with pytest.raises(MetricError, match="completion_authority must be bool"):
        MetricDefinition(
            "METRIC.X",
            MetricClass.OUTCOME,
            "count",
            "events",
            1,  # type: ignore[arg-type]
        )


def test_registry_binds_unbound_observation_to_exact_definition_revision() -> None:
    subject = definition()
    raw = observation()
    assert raw.definition_digest is None
    metric = MetricRegistry((subject,)).observe(raw)
    assert metric.observation.definition_digest == subject.digest


def test_explicit_stale_definition_revision_is_rejected() -> None:
    subject = definition()
    with pytest.raises(MetricError, match="definition revision mismatch"):
        MetricRegistry((subject,)).observe(
            observation(definition_digest="0" * 64)
        )


def test_explicit_source_kind_mismatch_is_rejected() -> None:
    subject = definition(source_kind="signed-evidence")
    with pytest.raises(MetricError, match="source kind mismatch"):
        MetricRegistry((subject,)).observe(
            observation(source_kind="unsigned-log")
        )


def test_direct_project_metric_requires_bound_observation() -> None:
    with pytest.raises(MetricError, match="definition revision mismatch"):
        ProjectMetric(definition(), observation())


def test_incomplete_observation_cannot_become_metric() -> None:
    with pytest.raises(MetricError, match="incomplete observation"):
        MetricRegistry((definition(),)).observe(
            observation(complete=False)
        )


def test_ratio_value_must_equal_integer_provenance() -> None:
    registry = MetricRegistry((definition(unit="ratio"),))
    good = registry.observe(
        observation(value=0.9, numerator=9, denominator=10)
    )
    assert good.observation.value == 0.9

    with pytest.raises(MetricError, match="ratio value"):
        registry.observe(
            observation(value=0.99, numerator=9, denominator=10)
        )


def test_ratio_numerator_cannot_exceed_denominator() -> None:
    registry = MetricRegistry((definition(unit="ratio"),))
    with pytest.raises(MetricError, match="numerator cannot exceed"):
        registry.observe(
            observation(value=1.1, numerator=11, denominator=10)
        )


def test_percent_value_must_equal_integer_provenance() -> None:
    registry = MetricRegistry((definition(unit="percent"),))
    metric = registry.observe(
        observation(value=90.0, numerator=9, denominator=10)
    )
    assert metric.observation.value == 90.0

    with pytest.raises(MetricError, match="percent value"):
        registry.observe(
            observation(value=9.0, numerator=9, denominator=10)
        )


def test_count_value_and_denominator_are_exact() -> None:
    registry = MetricRegistry((definition(unit="count"),))
    metric = registry.observe(
        observation(value=9, numerator=9, denominator=1)
    )
    assert metric.observation.value == 9.0

    with pytest.raises(MetricError, match="denominator must equal one"):
        registry.observe(
            observation(value=9, numerator=9, denominator=10)
        )

    with pytest.raises(MetricError, match="count value"):
        registry.observe(
            observation(value=8, numerator=9, denominator=1)
        )


def test_zero_denominator_rejected_before_metric_binding() -> None:
    with pytest.raises(MetricError, match="denominator must be positive"):
        observation(denominator=0)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_non_finite_values_rejected(bad: float) -> None:
    with pytest.raises(MetricError, match="finite number"):
        observation(value=bad)


def test_numeric_boolean_aliases_fail_closed() -> None:
    with pytest.raises(MetricError, match="finite number"):
        observation(value=True)  # type: ignore[arg-type]
    with pytest.raises(MetricError, match="numerator"):
        observation(numerator=True)  # type: ignore[arg-type]
    with pytest.raises(MetricError, match="denominator"):
        observation(denominator=True)  # type: ignore[arg-type]
    with pytest.raises(MetricError, match="observed_tick"):
        observation(observed_tick=True)  # type: ignore[arg-type]


def test_source_digest_must_be_lowercase_sha256() -> None:
    with pytest.raises(MetricError, match="source_digest"):
        observation(source_digest="NOT-A-DIGEST")


def test_metric_freshness_uses_definition_policy() -> None:
    metric = MetricRegistry(
        (definition(max_age_ticks=10),)
    ).observe(observation(observed_tick=5))
    assert metric.freshness(15) is MetricFreshness.FRESH
    assert metric.freshness(16) is MetricFreshness.STALE
    assert metric.freshness(4) is MetricFreshness.FUTURE


def test_registry_stale_uses_definition_age_by_default() -> None:
    registry = MetricRegistry((definition(max_age_ticks=10),))
    metric = registry.observe(observation(observed_tick=5))
    assert registry.stale(metric, 15) is False
    assert registry.stale(metric, 16) is True


def test_registry_stale_supports_explicit_diagnostic_age_without_mutating_definition() -> None:
    registry = MetricRegistry((definition(max_age_ticks=10),))
    metric = registry.observe(observation(observed_tick=5))
    assert registry.stale(metric, 8, 2) is True
    assert metric.definition.max_age_ticks == 10


def test_registry_stale_rejects_current_tick_before_observation() -> None:
    registry = MetricRegistry((definition(),))
    metric = registry.observe(observation(observed_tick=5))
    with pytest.raises(MetricError, match="predates observation"):
        registry.stale(metric, 4)


def test_duplicate_metric_definition_rejected() -> None:
    subject = definition()
    with pytest.raises(MetricError, match="duplicate metric definition"):
        MetricRegistry((subject, subject))


def test_empty_registry_rejected() -> None:
    with pytest.raises(MetricError, match="non-empty"):
        MetricRegistry(())


def test_registry_identity_is_definition_order_independent() -> None:
    first = definition(
        metric_id="METRIC.A",
        metric_class=MetricClass.ACTIVITY,
    )
    second = definition(
        metric_id="METRIC.B",
        metric_class=MetricClass.OUTCOME,
    )
    assert MetricRegistry((first, second)).digest == (
        MetricRegistry((second, first)).digest
    )


def test_definition_revision_changes_registry_identity() -> None:
    original = MetricRegistry((definition(max_age_ticks=10),)).digest
    revised = MetricRegistry((definition(max_age_ticks=11),)).digest
    assert original != revised


def test_snapshot_reports_missing_and_stale_metrics_explicitly() -> None:
    quality = definition(
        metric_id="METRIC.QUALITY",
        metric_class=MetricClass.QUALITY,
        max_age_ticks=5,
    )
    risk = definition(
        metric_id="METRIC.RISK",
        metric_class=MetricClass.RISK,
        max_age_ticks=5,
    )
    outcome = definition(
        metric_id="METRIC.OUTCOME",
        metric_class=MetricClass.OUTCOME,
        max_age_ticks=5,
    )
    registry = MetricRegistry((quality, risk, outcome))
    snapshot = registry.snapshot(
        (
            observation(
                metric_id="METRIC.QUALITY",
                observed_tick=10,
            ),
            observation(
                metric_id="METRIC.RISK",
                observed_tick=1,
            ),
        ),
        current_tick=10,
    )
    assert snapshot.missing_metric_ids == ("METRIC.OUTCOME",)
    assert snapshot.stale_metric_ids == ("METRIC.RISK",)
    assert snapshot.diagnostic_only is True

    summaries = {
        item.metric_class: item
        for item in snapshot.class_summaries
    }
    assert summaries[MetricClass.QUALITY].fresh == 1
    assert summaries[MetricClass.RISK].stale == 1
    assert summaries[MetricClass.OUTCOME].missing == 1


def test_snapshot_rejects_duplicate_metric_observation() -> None:
    registry = MetricRegistry((definition(),))
    with pytest.raises(MetricError, match="duplicate metric observation"):
        registry.snapshot(
            (observation(), observation()),
            current_tick=5,
        )


def test_snapshot_rejects_unknown_metric_observation() -> None:
    registry = MetricRegistry((definition(),))
    with pytest.raises(MetricError, match="unknown metric"):
        registry.snapshot(
            (
                observation(
                    metric_id="METRIC.UNKNOWN",
                ),
            ),
            current_tick=5,
        )


def test_snapshot_rejects_future_observation() -> None:
    registry = MetricRegistry((definition(),))
    with pytest.raises(MetricError, match="future observation"):
        registry.snapshot(
            (observation(observed_tick=6),),
            current_tick=5,
        )


def test_snapshot_identity_is_observation_order_independent() -> None:
    first = definition(
        metric_id="METRIC.A",
        metric_class=MetricClass.ACTIVITY,
    )
    second = definition(
        metric_id="METRIC.B",
        metric_class=MetricClass.OUTCOME,
    )
    registry = MetricRegistry((first, second))
    a = observation(
        metric_id="METRIC.A",
        source_digest=sha("a"),
    )
    b = observation(
        metric_id="METRIC.B",
        source_digest=sha("b"),
    )
    one = registry.snapshot((a, b), current_tick=5)
    two = registry.snapshot((b, a), current_tick=5)
    assert one.digest == two.digest


def test_snapshot_identity_changes_with_source_provenance() -> None:
    registry = MetricRegistry((definition(),))
    one = registry.snapshot(
        (
            observation(
                source_digest=sha("source-a"),
            ),
        ),
        current_tick=5,
    )
    two = registry.snapshot(
        (
            observation(
                source_digest=sha("source-b"),
            ),
        ),
        current_tick=5,
    )
    assert one.digest != two.digest


def test_snapshot_diagnostic_only_cannot_be_reinterpreted_as_completion() -> None:
    snapshot = MetricRegistry((definition(),)).snapshot(
        (observation(),),
        current_tick=5,
    )
    assert snapshot.diagnostic_only is True
    assert not hasattr(snapshot, "complete")
    assert not hasattr(snapshot, "eligible")
    assert not hasattr(snapshot, "approved")


def test_trend_orders_observations_by_tick_and_reports_delta() -> None:
    registry = MetricRegistry((definition(),))
    trend = registry.trend(
        "METRIC.TEST",
        (
            observation(
                value=0.8,
                numerator=8,
                denominator=10,
                observed_tick=10,
                source_digest=sha("later"),
            ),
            observation(
                value=0.5,
                numerator=5,
                denominator=10,
                observed_tick=1,
                source_digest=sha("first"),
            ),
        ),
    )
    assert trend.first_tick == 1
    assert trend.last_tick == 10
    assert trend.first_value == 0.5
    assert trend.last_value == 0.8
    assert trend.delta == pytest.approx(0.3)


def test_trend_identity_is_input_order_independent() -> None:
    registry = MetricRegistry((definition(),))
    early = observation(
        value=0.5,
        numerator=5,
        denominator=10,
        observed_tick=1,
        source_digest=sha("early"),
    )
    late = observation(
        value=0.8,
        numerator=8,
        denominator=10,
        observed_tick=2,
        source_digest=sha("late"),
    )
    assert registry.trend(
        "METRIC.TEST",
        (early, late),
    ).digest == registry.trend(
        "METRIC.TEST",
        (late, early),
    ).digest


def test_trend_rejects_duplicate_observation_tick() -> None:
    registry = MetricRegistry((definition(),))
    with pytest.raises(MetricError, match="duplicate observation tick"):
        registry.trend(
            "METRIC.TEST",
            (
                observation(
                    value=0.5,
                    numerator=5,
                    denominator=10,
                    observed_tick=1,
                    source_digest=sha("one"),
                ),
                observation(
                    value=0.6,
                    numerator=6,
                    denominator=10,
                    observed_tick=1,
                    source_digest=sha("two"),
                ),
            ),
        )


def test_trend_rejects_foreign_metric_observation() -> None:
    definitions = (
        definition(metric_id="METRIC.A"),
        definition(metric_id="METRIC.B"),
    )
    registry = MetricRegistry(definitions)
    with pytest.raises(MetricError, match="foreign metric"):
        registry.trend(
            "METRIC.A",
            (
                observation(metric_id="METRIC.A"),
                observation(metric_id="METRIC.B"),
            ),
        )


def test_trend_requires_at_least_one_observation() -> None:
    with pytest.raises(MetricError, match="requires observations"):
        MetricRegistry((definition(),)).trend("METRIC.TEST", ())


def test_unknown_metric_query_fails_with_domain_error() -> None:
    with pytest.raises(MetricError, match="unknown metric"):
        MetricRegistry((definition(),)).definition("METRIC.UNKNOWN")


def test_observe_requires_typed_observation() -> None:
    with pytest.raises(TypeError, match="MetricObservation"):
        MetricRegistry((definition(),)).observe(
            "METRIC.TEST"  # type: ignore[arg-type]
        )


def test_snapshot_requires_typed_observation_collection() -> None:
    with pytest.raises(TypeError, match="MetricObservation"):
        MetricRegistry((definition(),)).snapshot(
            ("METRIC.TEST",),  # type: ignore[arg-type]
            current_tick=5,
        )


def test_definition_owner_unit_source_and_description_are_canonical() -> None:
    with pytest.raises(MetricError, match="owner_id"):
        definition(owner_id="owner.lower")
    with pytest.raises(MetricError, match="unit"):
        definition(unit="Ratio With Spaces")
    with pytest.raises(MetricError, match="source_kind"):
        definition(source_kind="Signed Evidence")
    with pytest.raises(MetricError, match="description"):
        MetricDefinition(
            "METRIC.X",
            MetricClass.QUALITY,
            "ratio",
            "signed-evidence",
            description=" padded ",
        )


def test_metric_digest_binds_definition_and_source_revision() -> None:
    registry = MetricRegistry((definition(),))
    first = registry.observe(
        observation(source_digest=sha("a"))
    )
    second = registry.observe(
        observation(source_digest=sha("b"))
    )
    assert first.digest != second.digest
