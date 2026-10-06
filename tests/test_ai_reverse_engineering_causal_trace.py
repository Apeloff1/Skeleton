from __future__ import annotations

from hashlib import sha256

from skeleton.ai.research.model_internals.reverse_engineering.causal_trace import (
    CausalTraceObservation,
    analyze_causal_trace,
)
from skeleton.ai.research.model_internals.reverse_engineering.feature_specialization import (
    FeatureUnitObservation,
    analyze_feature_specialization,
)


def d(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def test_causal_trace_identifies_high_restoration_layer():
    report = analyze_causal_trace(
        (
            CausalTraceObservation("a", d("in-a"), 10, 1.0, 0.2, 0.9, d("edit-a")),
            CausalTraceObservation("b", d("in-b"), 10, 1.0, 0.4, 0.85, d("edit-b")),
        )
    )[0]
    assert report.layer_index == 10
    assert report.positive_restoration_ratio == 1.0
    assert report.mean_restoration_fraction is not None
    assert report.mean_restoration_fraction > 0.8
    assert report.over_restoration_ratio == 0.0


def test_feature_specialization_finds_consistent_unit():
    feature = d("feature")
    report = analyze_feature_specialization(
        (
            FeatureUnitObservation("a", feature, "l1", "u1", 0.9, d("a")),
            FeatureUnitObservation("b", feature, "l1", "u1", 0.8, d("b")),
            FeatureUnitObservation("c", feature, "l1", "u2", 0.2, d("c")),
            FeatureUnitObservation("d", feature, "l2", "u3", -0.1, d("d")),
        )
    )[0]
    assert report.top_layer_id == "l1"
    assert report.top_unit_id == "u1"
    assert abs(report.top_mean_score - 0.85) < 1e-12
    assert report.score_concentration > 0.7
    assert report.unit_count == 3
