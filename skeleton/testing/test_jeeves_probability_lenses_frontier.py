import math

from skeleton.jeeves.agent.probability_lenses import (
    ProbabilityLens,
    ProbabilityWorkbench,
    aleatoric_epistemic_assessment,
    conformal_coverage_assessment,
    expected_information_gain,
    fair_dice_sum_probability,
    hypergeometric_probability,
    memory_pair_next_flip_probability,
    robust_bayes_envelope,
    surprisal_probability,
)


def test_probability_taxonomy_expands_without_erasing_original_lenses():
    values = ProbabilityWorkbench.lenses()
    assert len(values) >= 30
    assert ProbabilityLens.CLASSICAL in values
    assert ProbabilityLens.BAYESIAN in values
    assert ProbabilityLens.MEMORY_RETRIEVAL in values
    assert ProbabilityLens.CONFORMAL_COVERAGE in values
    assert ProbabilityLens.ROBUST_BAYES in values


def test_exact_two_d6_probability_is_one_sixth():
    assessment = fair_dice_sum_probability(2, 6, minimum_sum=7, maximum_sum=7)
    assert assessment.estimate is not None
    assert math.isclose(assessment.estimate, 1.0 / 6.0, rel_tol=1e-12)
    assert assessment.metadata["exact"] is True


def test_hypergeometric_without_replacement_is_exact():
    assessment = hypergeometric_probability(52, 4, 5, 1)
    expected = math.comb(4, 1) * math.comb(48, 4) / math.comb(52, 5)
    assert assessment.estimate is not None
    assert math.isclose(assessment.estimate, expected, rel_tol=1e-12)


def test_memory_game_probability_is_conditional_on_information_state():
    assessment = memory_pair_next_flip_probability(
        10,
        2,
        3,
        targeting_known_singleton=False,
    )
    # 16 cards remain after two complete pairs are removed; three remembered
    # singletons leave 13 face-down unknown locations.
    assert assessment.estimate is not None
    assert math.isclose(assessment.estimate, 3.0 / 13.0, rel_tol=1e-12)
    assert assessment.metadata["conditional_on_correct_memory"] is True


def test_information_gain_keeps_information_units_out_of_probability_scalar():
    assessment = expected_information_gain(
        (0.5, 0.5),
        (
            (0.5, (0.9, 0.1)),
            (0.5, (0.1, 0.9)),
        ),
    )
    assert assessment.estimate is not None
    assert 0.0 < assessment.estimate < 1.0
    assert assessment.metadata["information_gain_bits"] > 0.0


def test_conformal_assessment_exposes_exchangeability_requirement():
    assessment = conformal_coverage_assessment(94, 100, target_coverage=0.90)
    assert assessment.calibrated is True
    assert assessment.metadata["exchangeability_required_for_nominal_guarantee"] is True
    assert assessment.lower <= 0.94 <= assessment.upper


def test_robust_bayes_returns_envelope_not_false_precision():
    assessment = robust_bayes_envelope((0.35, 0.51, 0.68))
    assert assessment.estimate is None
    assert assessment.lower == 0.35
    assert assessment.upper == 0.68


def test_aleatoric_epistemic_split_and_surprisal_are_explicit():
    split = aleatoric_epistemic_assessment(0.25, 0.10)
    assert split.estimate is not None
    assert math.isclose(split.estimate, 0.6, rel_tol=1e-12)
    surprise = surprisal_probability(0.125)
    assert surprise.metadata["surprisal"] == 3.0
