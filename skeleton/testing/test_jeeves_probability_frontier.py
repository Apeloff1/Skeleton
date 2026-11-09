from __future__ import annotations

import math

import pytest

from skeleton.jeeves.agent.probability_frontier import (
    FrontierProbabilityLens,
    FrontierProbabilityWorkbench,
    anytime_hoeffding_interval,
    competing_risk_probability,
    conformal_error_bound,
    distribution_shift_bound,
    frechet_joint_bounds,
    generalized_pareto_tail_probability,
    importance_sampling_probability,
    information_directed_score,
    log_opinion_pool,
    model_mixture_probability,
    partial_identification_interval,
    poisson_at_least_one,
    retrieval_competition_probability,
    robust_ambiguity_probability,
    sequential_e_value,
    split_conformal_p_value,
    system_reliability,
    uncertainty_decomposition,
)
from skeleton.jeeves.agent.probability_lenses import AssessmentShape, ProbabilityError


def test_frontier_registry_is_orthogonal_and_explicit() -> None:
    lenses = FrontierProbabilityWorkbench.lenses()
    assert len(lenses) == 18
    assert len(set(lenses)) == len(lenses)
    assert FrontierProbabilityLens.CONFORMAL_COVERAGE in lenses
    assert FrontierProbabilityLens.SEQUENTIAL_E_VALUE in lenses
    assert FrontierProbabilityLens.DISTRIBUTION_SHIFT in lenses
    assert FrontierProbabilityLens.RETRIEVAL_COMPETITION in lenses


def test_split_conformal_is_rank_evidence_not_posterior_probability() -> None:
    result = split_conformal_p_value([0.1, 0.2, 0.4, 0.8], 0.35)
    assert result.shape is AssessmentShape.EVIDENCE_WEIGHT
    assert result.estimate == pytest.approx(3.0 / 5.0)
    assert result.target == "conformal_rank_p_value"
    assert result.metadata["posterior_probability"] is False
    coverage = conformal_error_bound(0.1)
    assert coverage.estimate == pytest.approx(0.9)
    assert "exchangeability" in coverage.assumptions


def test_e_value_keeps_raw_anytime_evidence_separate_from_probability() -> None:
    result = sequential_e_value([2.0, 1.5, 4.0])
    assert result.metadata["e_value"] == pytest.approx(12.0)
    assert result.estimate == pytest.approx(12.0 / 13.0)
    assert result.metadata["posterior_probability"] is False
    zero = sequential_e_value([2.0, 0.0, 4.0])
    assert zero.metadata["e_value"] == 0.0
    assert zero.estimate == 0.0


def test_anytime_interval_is_bounded_and_declares_look_budget() -> None:
    result = anytime_hoeffding_interval(0.6, 500, delta=0.05, looks=20)
    assert result.lower is not None and result.upper is not None
    assert 0.0 <= result.lower <= result.estimate <= result.upper <= 1.0
    assert result.metadata["looks"] == 20
    assert result.confidence == pytest.approx(0.95)


def test_frechet_bounds_do_not_assume_independence() -> None:
    result = frechet_joint_bounds(0.8, 0.7)
    assert result.lower == pytest.approx(0.5)
    assert result.upper == pytest.approx(0.7)
    assert result.metadata["independence_not_assumed"] is True
    independence = 0.8 * 0.7
    assert result.lower <= independence <= result.upper


def test_distribution_shift_expands_source_point_into_robust_interval() -> None:
    result = distribution_shift_bound(0.62, 0.08)
    assert result.estimate == pytest.approx(0.62)
    assert result.lower == pytest.approx(0.54)
    assert result.upper == pytest.approx(0.70)
    assert result.target == "target_domain_event_probability"


def test_uncertainty_decomposition_obeys_total_variance_identity() -> None:
    result = uncertainty_decomposition([0.1, 0.5, 0.9], [0.2, 0.3, 0.5])
    total = result.metadata["total_variance"]
    aleatoric = result.metadata["aleatoric_variance"]
    epistemic = result.metadata["epistemic_variance"]
    assert total == pytest.approx(aleatoric + epistemic, abs=1e-12)
    assert abs(result.metadata["identity_residual"]) < 1e-12


def test_model_mixture_and_ambiguity_set_keep_different_semantics() -> None:
    mixture = model_mixture_probability([0.2, 0.8], [0.75, 0.25])
    robust = robust_ambiguity_probability([0.2, 0.8])
    assert mixture.estimate == pytest.approx(0.35)
    assert robust.estimate is None
    assert robust.lower == pytest.approx(0.2)
    assert robust.upper == pytest.approx(0.8)
    assert mixture.target != robust.target


def test_reliability_series_and_parallel_behave_differently() -> None:
    series = system_reliability([0.9, 0.8], topology="series")
    parallel = system_reliability([0.9, 0.8], topology="parallel")
    assert series.estimate == pytest.approx(0.72)
    assert parallel.estimate == pytest.approx(0.98)
    assert series.estimate < parallel.estimate


def test_arrival_competing_risk_and_extreme_tail_are_bounded() -> None:
    arrival = poisson_at_least_one(0.5, 2.0)
    assert arrival.estimate == pytest.approx(1.0 - math.exp(-1.0))
    competing = competing_risk_probability(0.2, [0.1, 0.05], 3.0)
    assert competing.estimate is not None and 0.0 < competing.estimate < 1.0
    tail = generalized_pareto_tail_probability(0.1, 4.0, scale=2.0, shape=0.1)
    assert tail.estimate is not None and 0.0 <= tail.estimate <= 0.1


def test_importance_sampling_reports_effective_sample_size() -> None:
    result = importance_sampling_probability([1, 0, 1, 0], [10.0, 1.0, 10.0, 1.0])
    assert result.estimate == pytest.approx(20.0 / 22.0)
    assert result.effective_samples is not None
    assert 1.0 < result.effective_samples < 4.0
    assert result.metadata["raw_samples"] == 4


def test_information_directed_score_rewards_information_at_equal_regret() -> None:
    low_info = information_directed_score(0.3, 0.05)
    high_info = information_directed_score(0.3, 0.5)
    assert low_info.estimate is not None and high_info.estimate is not None
    assert high_info.estimate > low_info.estimate
    assert high_info.metadata["event_probability"] is False


def test_partial_identification_refuses_false_point_precision() -> None:
    result = partial_identification_interval(0.25, 0.65, estimand="P(outcome under policy)")
    assert result.shape is AssessmentShape.INTERVAL
    assert result.estimate is None
    assert result.metadata["point_identified"] is False
    with pytest.raises(ProbabilityError):
        partial_identification_interval(0.8, 0.2, estimand="bad")


def test_log_pool_requires_common_target_at_the_call_site() -> None:
    pooled = log_opinion_pool([0.8, 0.6], [0.5, 0.5])
    assert pooled.estimate is not None
    assert 0.6 < pooled.estimate < 0.8
    assert "same proposition" in pooled.assumptions


def test_retrieval_competition_is_normalized_choice_probability() -> None:
    target = retrieval_competition_probability([2.0, 0.0, -1.0], 0)
    weaker = retrieval_competition_probability([2.0, 0.0, -1.0], 2)
    assert target.estimate is not None and weaker.estimate is not None
    assert target.estimate > weaker.estimate
    probs = [retrieval_competition_probability([2.0, 0.0, -1.0], i).estimate for i in range(3)]
    assert sum(value for value in probs if value is not None) == pytest.approx(1.0)


def test_pooling_guard_rejects_mismatched_targets() -> None:
    left = distribution_shift_bound(0.5, 0.1)
    right = conformal_error_bound(0.1)
    assert not FrontierProbabilityWorkbench.compatible_for_pooling([left, right])
    a = model_mixture_probability([0.4, 0.6])
    b = model_mixture_probability([0.3, 0.7])
    assert FrontierProbabilityWorkbench.compatible_for_pooling([a, b])
