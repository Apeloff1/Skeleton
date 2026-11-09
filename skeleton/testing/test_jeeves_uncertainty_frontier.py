from __future__ import annotations

import math

from skeleton.jeeves.agent.uncertainty_frontier import (
    BayesianCategorical,
    DecisionCalibration,
    DependenceDiagnostics,
    FrontierLens,
    FrontierLensRegistry,
    GameProbability,
    IdentificationDiagnostics,
    ImplementationStatus,
    InfluenceDiagnostics,
    MemoryUncertainty,
    MonteCarloDiagnostics,
    QuantityKind,
    SequentialInference,
)


def test_registry_separates_reference_algorithms_from_adapter_required_contracts() -> None:
    registry = FrontierLensRegistry()
    assert len(registry.all()) >= 40
    assert registry.get(FrontierLens.E_VALUE).implementation is ImplementationStatus.REFERENCE
    assert registry.get(FrontierLens.GAUSSIAN_PROCESS_PREDICTIVE).implementation is ImplementationStatus.ADAPTER_REQUIRED
    assert registry.get(FrontierLens.PARTIAL_IDENTIFICATION).quantity is QuantityKind.IDENTIFICATION_SET
    assert registry.reference_implemented()


def test_dirichlet_posterior_is_normalized_and_updates_toward_counts() -> None:
    measurement = BayesianCategorical.dirichlet_posterior((9, 1), prior=(1, 1))
    posterior = measurement.metadata["posterior_mean"]
    assert math.isclose(sum(posterior), 1.0)
    assert posterior[0] > posterior[1]
    assert measurement.sample_size == 10.0


def test_beta_binomial_predictive_reports_future_count_uncertainty() -> None:
    measurement = BayesianCategorical.beta_binomial_predictive(8, 2, future_trials=10)
    assert 0.0 < measurement.value < 10.0
    assert measurement.metadata["predictive_variance"] > 0.0


def test_opponent_model_bayes_update_favors_more_likely_type() -> None:
    measurement = BayesianCategorical.opponent_posterior((0.5, 0.5), (0.9, 0.1))
    posterior = measurement.metadata["posterior"]
    assert posterior[0] > 0.8
    assert posterior[1] < 0.2


def test_e_value_keeps_anytime_semantics_explicit() -> None:
    measurement = SequentialInference.e_value((2.0, 2.0, 2.0, 2.0, 2.0), alpha=0.05)
    assert measurement.quantity is QuantityKind.E_VALUE
    assert measurement.value == 32.0
    assert measurement.metadata["crosses_threshold"] is True
    assert "valid e-process" in measurement.assumptions[0]


def test_confidence_sequence_is_time_indexed_and_bounded() -> None:
    sequence = SequentialInference.bounded_mean_confidence_sequence((1.0, 0.0, 1.0, 1.0, 0.0), alpha=0.05)
    assert len(sequence) == 5
    assert all(item.quantity is QuantityKind.CONFIDENCE_SEQUENCE for item in sequence)
    assert all(0.0 <= item.lower <= item.upper <= 1.0 for item in sequence)
    assert sequence[-1].sample_size == 5.0


def test_manski_bounds_refuse_false_point_identification() -> None:
    measurement = IdentificationDiagnostics.manski_missing_binary(40, 40, 20)
    assert math.isclose(measurement.lower, 0.4)
    assert math.isclose(measurement.upper, 0.6)
    assert measurement.quantity is QuantityKind.IDENTIFICATION_SET


def test_credal_envelope_preserves_model_ambiguity() -> None:
    measurement = IdentificationDiagnostics.credal_envelope(((0.2, 0.8), (0.7, 0.3)), event_index=0)
    assert measurement.lower == 0.2
    assert measurement.upper == 0.7


def test_mutual_information_detects_perfect_binary_dependence() -> None:
    measurement = DependenceDiagnostics.mutual_information(((10, 0), (0, 10)))
    assert measurement.value > 0.99
    assert measurement.metadata["bits"] > 0.99


def test_importance_weight_ess_falls_when_one_sample_dominates() -> None:
    balanced = MonteCarloDiagnostics.importance_weight_ess((1, 1, 1, 1))
    concentrated = MonteCarloDiagnostics.importance_weight_ess((100, 1, 1, 1))
    assert balanced.value == 4.0
    assert concentrated.value < balanced.value


def test_rare_event_importance_sampling_reports_ess_not_fake_precision() -> None:
    measurement = MonteCarloDiagnostics.rare_event_self_normalized((0, 0, 1), (0.0, 0.0, math.log(10.0)))
    assert 0.0 < measurement.value < 1.0
    assert measurement.metadata["ess"] < 3.0
    assert measurement.metadata["unbiased"] is False


def test_heterogeneous_dice_exact_probability() -> None:
    measurement = GameProbability.dice_event((6, 8), minimum_sum=14, maximum_sum=14)
    # Only 6+8 reaches 14, so one microstate out of 48.
    assert math.isclose(measurement.value, 1.0 / 48.0)
    assert measurement.metadata["exact"] is True


def test_hypergeometric_exact_without_replacement() -> None:
    measurement = GameProbability.hypergeometric_exact(52, 4, 5, exactly=1)
    expected = math.comb(4, 1) * math.comb(48, 4) / math.comb(52, 5)
    assert math.isclose(measurement.value, expected)


def test_markov_hitting_probability_counts_first_hit_mass_once() -> None:
    transition = (
        (0.5, 0.5),
        (0.0, 1.0),
    )
    measurement = GameProbability.markov_hitting_probability(transition, start=0, targets=(1,), horizon=2)
    assert math.isclose(measurement.value, 0.75)


def test_memory_cue_competition_reduces_retrieval_without_leaving_probability_domain() -> None:
    measurement = MemoryUncertainty.cue_competition(0.8, (0.7, 0.5), competition_scale=1.0)
    assert 0.0 < measurement.value < 0.8


def test_memory_interference_keeps_proactive_and_retroactive_channels_visible() -> None:
    measurement = MemoryUncertainty.interference(
        target_similarity=0.9,
        proactive_similarity=0.8,
        retroactive_similarity=0.2,
        temporal_overlap=0.7,
    )
    assert 0.0 <= measurement.value <= 1.0
    assert measurement.metadata["proactive_risk"] > measurement.metadata["retroactive_risk"]


def test_decision_weighted_calibration_is_not_plain_average_brier() -> None:
    measurement = DecisionCalibration.weighted_brier((0.9, 0.9), (1, 0), (10.0, 1.0))
    assert measurement.value < 0.1
    assert measurement.metadata["score"] == "weighted_brier"


def test_jackknife_exposes_high_influence_observation() -> None:
    measurement = InfluenceDiagnostics.jackknife_mean((1.0, 1.0, 1.0, 10.0))
    assert measurement.value > 0.0
    assert max(abs(x) for x in measurement.metadata["influences"]) == measurement.value
