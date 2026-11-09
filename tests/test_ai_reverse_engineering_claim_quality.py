from __future__ import annotations

from hashlib import sha256

from skeleton.ai.research.model_internals.reverse_engineering.attribution_stability import (
    AttributionSnapshot,
    analyze_attribution_stability,
)
from skeleton.ai.research.model_internals.reverse_engineering.counterfactual_consistency import (
    CounterfactualPair,
    analyze_counterfactual_consistency,
)
from skeleton.ai.research.model_internals.reverse_engineering.effect_size import (
    ScalarMeasurement,
    estimate_effect_size,
)
from skeleton.ai.research.model_internals.reverse_engineering.intervention_localization import (
    LayerInterventionEffect,
    analyze_intervention_localization,
)


def d(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def test_attribution_stability_measures_repeated_topk_overlap():
    probe = d("probe")
    report = analyze_attribution_stability(
        (
            AttributionSnapshot("a", probe, ("f1", "f2", "f3")),
            AttributionSnapshot("b", probe, ("f1", "f2", "f4")),
            AttributionSnapshot("c", probe, ("f1", "f2", "f5")),
        )
    )
    assert report.universal_feature_count == 2
    assert report.majority_feature_count == 2
    assert report.min_pairwise_jaccard == 0.5
    assert report.mean_pairwise_jaccard == 0.5


def test_intervention_localization_finds_peak_layer():
    probe = d("probe")
    report = analyze_intervention_localization(
        (
            LayerInterventionEffect("a", probe, 1, 0.1),
            LayerInterventionEffect("b", probe, 1, 0.2),
            LayerInterventionEffect("c", probe, 5, 0.8),
            LayerInterventionEffect("d", probe, 5, 1.0),
            LayerInterventionEffect("e", probe, 9, 0.1),
        )
    )
    assert report.peak_layer == 5
    assert report.peak_mean_effect == 0.9
    assert report.sign_consistency_at_peak == 1.0
    assert report.absolute_effect_concentration > 0.7


def test_counterfactual_consistency_distinguishes_change_and_invariance():
    report = analyze_counterfactual_consistency(
        (
            CounterfactualPair("a", d("ia"), d("ica"), d("oa"), d("oca"), True),
            CounterfactualPair("b", d("ib"), d("icb"), d("ob"), d("ocb"), True),
            CounterfactualPair("c", d("ic"), d("icc"), d("same"), d("same"), False),
            CounterfactualPair("d", d("id"), d("icd"), d("same2"), d("same2"), False),
        )
    )
    assert report.change_sensitivity == 1.0
    assert report.invariance_specificity == 1.0
    assert report.overall_consistency == 1.0


def test_effect_size_recovers_large_treatment_shift():
    report = estimate_effect_size(
        (
            ScalarMeasurement("c1", "control", 0.0),
            ScalarMeasurement("c2", "control", 1.0),
            ScalarMeasurement("c3", "control", 2.0),
            ScalarMeasurement("t1", "treatment", 3.0),
            ScalarMeasurement("t2", "treatment", 4.0),
            ScalarMeasurement("t3", "treatment", 5.0),
        ),
        control_group="control",
        treatment_group="treatment",
    )
    assert report.mean_difference == 3.0
    assert report.pooled_standard_deviation == 1.0
    assert report.standardized_effect == 3.0
