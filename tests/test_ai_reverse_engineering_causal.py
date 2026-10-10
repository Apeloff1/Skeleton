from __future__ import annotations

from hashlib import sha256

from skeleton.ai.research.model_internals.reverse_engineering.cache_eviction import (
    CacheTrial,
    analyze_cache_eviction,
)
from skeleton.ai.research.model_internals.reverse_engineering.expert_routing import (
    ExpertRoutingObservation,
    analyze_expert_routing,
)
from skeleton.ai.research.model_internals.reverse_engineering.residual_intervention import (
    ResidualInterventionObservation,
    analyze_residual_interventions,
)


def d(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def test_cache_eviction_finds_first_retention_loss():
    report = analyze_cache_eviction(
        (
            CacheTrial("a", 100, 50, 50, 1.0),
            CacheTrial("b", 100, 100, 100, 1.0),
            CacheTrial("c", 100, 150, 100, 0.8),
            CacheTrial("d", 100, 200, 100, 0.6),
        )
    )[0]
    assert report.first_over_capacity_units == 150
    assert report.first_retention_loss_units == 150
    assert report.monotonicity_violations == 0
    assert report.mean_retention_ratio < 1.0


def test_expert_routing_reports_top_k_and_load_concentration():
    report = analyze_expert_routing(
        (
            ExpertRoutingObservation("a", d("a"), 0, (0, 1), (0.7, 0.3)),
            ExpertRoutingObservation("b", d("b"), 0, (0, 2), (0.6, 0.4)),
            ExpertRoutingObservation("c", d("c"), 0, (0, 1), (0.8, 0.2)),
        )
    )[0]
    assert report.experts_seen == (0, 1, 2)
    assert report.top_k_values == (2,)
    assert report.selection_counts == ((0, 3), (1, 2), (2, 1))
    assert report.load_concentration > 1 / 3
    assert report.mean_weight_sum == 1.0


def test_residual_intervention_reports_consistent_causal_direction():
    report = analyze_residual_interventions(
        (
            ResidualInterventionObservation(
                "a", "layer-10", d("in-a"), d("control-a"), d("edit-a"), 0.2, 0.5, "steer"
            ),
            ResidualInterventionObservation(
                "b", "layer-10", d("in-b"), d("control-b"), d("edit-b"), 0.1, 0.4, "steer"
            ),
            ResidualInterventionObservation(
                "c", "layer-10", d("in-c"), d("control-c"), d("edit-c"), 0.0, 0.2, "steer"
            ),
        )
    )[0]
    assert report.changed_output_count == 3
    assert report.positive_delta_ratio == 1.0
    assert report.negative_delta_ratio == 0.0
    assert report.sign_consistency == 1.0
    assert report.mean_metric_delta > 0.0
